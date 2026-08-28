"""Dynamic analytics routes — day-wise and monthly production volume reports."""

from datetime import datetime, date

from flask import Blueprint, render_template, jsonify, request, send_file
from flask_login import login_required

from app.decorators import admin_required
from app.services.analytics_service import (
    generate_daywise_report,
    generate_monthly_report,
    export_analytics_excel,
)

analytics_bp = Blueprint("analytics", __name__)

_MAX_DAYWISE_DAYS   = 92   # ~one quarter
_MAX_MONTHLY_MONTHS = 36   # 3 years


def _parse_plant_codes() -> list | None:
    """Parse the optional ?plants=code1,code2 query param. Returns None if absent."""
    raw = request.args.get("plants", "").strip()
    if not raw:
        return None
    codes = [c.strip() for c in raw.split(",") if c.strip()]
    return codes if codes else None


# ── Page ──────────────────────────────────────────────────────────────────────

@analytics_bp.route("/analytics")
@admin_required
def analytics_page():
    return render_template("analytics.html")


# ── Day-wise API ──────────────────────────────────────────────────────────────

@analytics_bp.route("/api/analytics/daywise")
@admin_required
def api_analytics_daywise():
    from_str   = request.args.get("from")
    to_str     = request.args.get("to")
    hide_zero  = request.args.get("hide_zero", "false").lower() == "true"
    plant_codes = _parse_plant_codes()

    if not from_str or not to_str:
        return jsonify({"error": "'from' and 'to' query parameters are required"}), 400

    try:
        from_date = datetime.strptime(from_str, "%Y-%m-%d").date()
        to_date   = datetime.strptime(to_str,   "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    if from_date > to_date:
        return jsonify({"error": "'from' date must be on or before 'to' date"}), 400

    span = (to_date - from_date).days + 1
    if span > _MAX_DAYWISE_DAYS:
        return jsonify({
            "error": (
                f"Date range is {span} days — max is {_MAX_DAYWISE_DAYS}. "
                "Use the Monthly Summary tab for longer periods."
            )
        }), 400

    data = generate_daywise_report(from_date, to_date, hide_zero, plant_codes)
    return jsonify(data)


@analytics_bp.route("/api/analytics/daywise/export")
@admin_required
def api_analytics_daywise_export():
    from_str    = request.args.get("from")
    to_str      = request.args.get("to")
    hide_zero   = request.args.get("hide_zero", "false").lower() == "true"
    plant_codes = _parse_plant_codes()
    view        = "invoiced" if request.args.get("view") == "invoiced" else "production"

    try:
        from_date = datetime.strptime(from_str, "%Y-%m-%d").date()
        to_date   = datetime.strptime(to_str,   "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid dates"}), 400

    data = generate_daywise_report(from_date, to_date, hide_zero, plant_codes)
    buf  = export_analytics_excel(data, view=view)
    suffix = "_Invoiced" if view == "invoiced" else ""
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"Daywise_Volume_{from_date}_{to_date}{suffix}.xlsx",
    )


# ── Monthly API ───────────────────────────────────────────────────────────────

@analytics_bp.route("/api/analytics/monthly")
@admin_required
def api_analytics_monthly():
    from_str    = request.args.get("from")
    to_str      = request.args.get("to")
    hide_zero   = request.args.get("hide_zero", "false").lower() == "true"
    plant_codes = _parse_plant_codes()

    if not from_str or not to_str:
        return jsonify({"error": "'from' and 'to' query parameters are required"}), 400

    try:
        from_month = datetime.strptime(from_str, "%Y-%m-%d").date()
        to_month   = datetime.strptime(to_str,   "%Y-%m-%d").date()
    except ValueError:
        return jsonify({"error": "Invalid date format. Use YYYY-MM-DD"}), 400

    from_month = date(from_month.year, from_month.month, 1)
    to_month   = date(to_month.year,   to_month.month,   1)

    if from_month > to_month:
        return jsonify({"error": "'from' month must be on or before 'to' month"}), 400

    n_months = (to_month.year - from_month.year) * 12 + (to_month.month - from_month.month) + 1
    if n_months > _MAX_MONTHLY_MONTHS:
        return jsonify({
            "error": f"Month range is {n_months} months — max is {_MAX_MONTHLY_MONTHS}."
        }), 400

    data = generate_monthly_report(from_month, to_month, hide_zero, plant_codes)
    return jsonify(data)


@analytics_bp.route("/api/analytics/monthly/export")
@admin_required
def api_analytics_monthly_export():
    from_str    = request.args.get("from")
    to_str      = request.args.get("to")
    hide_zero   = request.args.get("hide_zero", "false").lower() == "true"
    plant_codes = _parse_plant_codes()
    view        = "invoiced" if request.args.get("view") == "invoiced" else "production"

    try:
        from_month = datetime.strptime(from_str, "%Y-%m-%d").date()
        to_month   = datetime.strptime(to_str,   "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid dates"}), 400

    from_month = date(from_month.year, from_month.month, 1)
    to_month   = date(to_month.year,   to_month.month,   1)

    data = generate_monthly_report(from_month, to_month, hide_zero, plant_codes)
    buf  = export_analytics_excel(data, view=view)
    suffix = "_Invoiced" if view == "invoiced" else ""
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"Monthly_Volume_{from_str[:7]}_{to_str[:7]}{suffix}.xlsx",
    )
