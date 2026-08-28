"""Public read-only JSON API for external applications.

  1. POST /api/v1/token             — username + password -> a Bearer token (valid 24h)
  2. GET  /api/v1/volumes/daily     — per-plant volume for one day
  3. GET  /api/v1/volumes/monthly   — per-plant volume for one month
  4. GET  /api/v1/volumes/yearly    — per-plant volume for one year, with a monthly breakdown

All three volume endpoints accept metric=produced|invoiced (default produced) and
only ever include active plants.

See API_DOCUMENTATION.html at the project root for full usage docs.
"""

from collections import defaultdict
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, request

from app import db
from app.decorators import api_token_required
from app.services.analytics_service import generate_daywise_report, generate_monthly_report
from app.services.api_tokens import authenticate, issue_token, TOKEN_LIFETIME_HOURS
from app.services.audit import log_action

api_v1_bp = Blueprint("api_v1", __name__)

# In-memory brute-force tracker for the token endpoint, mirroring the web login
# lockout in app/routes/auth.py — this route accepts a raw username/password too.
_failed_attempts: dict = defaultdict(list)
_MAX_ATTEMPTS = 5
_LOCKOUT_MINUTES = 15


def _is_locked_out(ip: str) -> tuple[bool, int]:
    cutoff = datetime.utcnow() - timedelta(minutes=_LOCKOUT_MINUTES)
    attempts = [t for t in _failed_attempts[ip] if t > cutoff]
    _failed_attempts[ip] = attempts
    if len(attempts) >= _MAX_ATTEMPTS:
        unlock_at = min(attempts) + timedelta(minutes=_LOCKOUT_MINUTES)
        remaining = max(0, int((unlock_at - datetime.utcnow()).total_seconds()))
        return True, remaining
    return False, 0


def _record_failure(ip: str):
    _failed_attempts[ip].append(datetime.utcnow())


def _clear_failures(ip: str):
    _failed_attempts.pop(ip, None)


@api_v1_bp.route("/api/v1/token", methods=["POST"])
def v1_get_token():
    """
    Exchange a username + password for a Bearer API token.

    Body: { "username": "...", "password": "..." }
    Response: { "token": "dvt_...", "token_type": "Bearer", "expires_at": "...", "expires_in_seconds": 86400 }
    """
    ip = request.remote_addr

    locked, remaining = _is_locked_out(ip)
    if locked:
        mins = (remaining // 60) + 1
        log_action("api_login_blocked", {"reason": "brute_force_lockout", "ip": ip})
        db.session.commit()
        return jsonify({"error": f"Too many failed attempts. Try again in {mins} minute(s)."}), 429

    data = request.get_json(silent=True) or {}
    username = (data.get("username") or "").strip()
    password = data.get("password") or ""

    if not username or not password:
        return jsonify({"error": "username and password are required"}), 400

    user = authenticate(username, password)
    if not user:
        _record_failure(ip)
        log_action("api_login_failed", {"username": username})
        db.session.commit()
        return jsonify({"error": "Invalid credentials"}), 401

    _clear_failures(ip)
    raw_token, token = issue_token(user)
    log_action("api_token_issued", {"username": user.username, "token_prefix": token.token_prefix})
    db.session.commit()

    return jsonify({
        "token": raw_token,
        "token_type": "Bearer",
        "expires_at": token.expires_at.isoformat(),
        "expires_in_seconds": TOKEN_LIFETIME_HOURS * 3600,
    })


# ── Volume data — daily / monthly / yearly ──────────────────────────────────

def _parse_metric():
    """Returns 'produced' or 'invoiced', or None if the query param is invalid."""
    m = request.args.get("metric", "produced").strip().lower()
    return m if m in ("produced", "invoiced") else None


def _plant_entry(p: dict, volume: float) -> dict:
    """Build the common per-plant response object from an analytics_service plant row."""
    return {
        "plant_code": p["plant_code"],
        "daily_tracker_name": p.get("daily_tracker_name", ""),
        "erp_name": p.get("erp_name", ""),
        "plant_name": p["plant_name"],
        "region": p["region"],
        "is_manual_entry": p.get("is_manual_entry", False),
        "volume": volume,
    }


@api_v1_bp.route("/api/v1/volumes/daily")
@api_token_required
def v1_volumes_daily():
    """
    Per-plant volume for a single day.

    Query params:
      - date (YYYY-MM-DD) — optional, defaults to today
      - metric (produced|invoiced) — optional, defaults to produced

    Response: { "period": "daily", "date": "...", "metric": "...", "count": N, "plants": [...] }
    """
    metric = _parse_metric()
    if metric is None:
        return jsonify({"error": "Invalid metric. Use 'produced' or 'invoiced'."}), 400

    date_str = request.args.get("date")
    try:
        target_date = date.fromisoformat(date_str) if date_str else date.today()
    except ValueError:
        return jsonify({"error": "Invalid date. Use YYYY-MM-DD."}), 400

    data = generate_daywise_report(target_date, target_date, hide_zero=False)
    vol_key = "invoiced_volumes" if metric == "invoiced" else "volumes"

    plants = []
    for region in data["regions"]:
        for p in region["plants"]:
            plants.append(_plant_entry(p, p[vol_key][0]))

    return jsonify({
        "period": "daily",
        "date": target_date.isoformat(),
        "metric": metric,
        "count": len(plants),
        "plants": plants,
    })


@api_v1_bp.route("/api/v1/volumes/monthly")
@api_token_required
def v1_volumes_monthly():
    """
    Per-plant volume for a single month.

    Query params:
      - month (YYYY-MM) — optional, defaults to the current month
      - metric (produced|invoiced) — optional, defaults to produced

    Response: { "period": "monthly", "month": "...", "metric": "...", "count": N, "plants": [...] }
    """
    metric = _parse_metric()
    if metric is None:
        return jsonify({"error": "Invalid metric. Use 'produced' or 'invoiced'."}), 400

    month_str = request.args.get("month")
    if month_str:
        try:
            year, month = month_str.split("-")
            month_date = date(int(year), int(month), 1)
        except (ValueError, AttributeError):
            return jsonify({"error": "Invalid month. Use YYYY-MM."}), 400
    else:
        today = date.today()
        month_date = date(today.year, today.month, 1)

    data = generate_monthly_report(month_date, month_date, hide_zero=False)
    vol_key = "invoiced_volumes" if metric == "invoiced" else "volumes"

    plants = []
    for region in data["regions"]:
        for p in region["plants"]:
            plants.append(_plant_entry(p, p[vol_key][0]))

    return jsonify({
        "period": "monthly",
        "month": month_date.isoformat(),
        "metric": metric,
        "count": len(plants),
        "plants": plants,
    })


@api_v1_bp.route("/api/v1/volumes/yearly")
@api_token_required
def v1_volumes_yearly():
    """
    Per-plant volume for a full calendar year (Jan-Dec), with a month-by-month breakdown.

    Query params:
      - year (YYYY) — optional, defaults to the current year
      - metric (produced|invoiced) — optional, defaults to produced

    Response: { "period": "yearly", "year": 2026, "metric": "...", "count": N, "plants": [
        { ...plant fields..., "volume": 62000.0, "monthly_breakdown": {"2026-01": 5100.0, ...} }
    ] }
    """
    metric = _parse_metric()
    if metric is None:
        return jsonify({"error": "Invalid metric. Use 'produced' or 'invoiced'."}), 400

    year_str = request.args.get("year")
    try:
        year = int(year_str) if year_str else date.today().year
        if not (2000 <= year <= 2100):
            raise ValueError
    except ValueError:
        return jsonify({"error": "Invalid year. Use a 4-digit year, e.g. 2026."}), 400

    from_month = date(year, 1, 1)
    to_month = date(year, 12, 1)
    data = generate_monthly_report(from_month, to_month, hide_zero=False)
    vol_key = "invoiced_volumes" if metric == "invoiced" else "volumes"
    tot_key = "invoiced_total" if metric == "invoiced" else "total"

    month_keys = [m[:7] for m in data["months"]]  # "YYYY-MM-01" -> "YYYY-MM"

    plants = []
    for region in data["regions"]:
        for p in region["plants"]:
            entry = _plant_entry(p, p[tot_key])
            entry["monthly_breakdown"] = dict(zip(month_keys, p[vol_key]))
            plants.append(entry)

    return jsonify({
        "period": "yearly",
        "year": year,
        "metric": metric,
        "count": len(plants),
        "plants": plants,
    })
