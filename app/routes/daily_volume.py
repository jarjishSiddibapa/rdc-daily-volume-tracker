"""Daily volume entry routes (manual entry + bulk)."""

import logging
from datetime import date, datetime, timedelta

import pytz
from flask import Blueprint, render_template, jsonify, request
from flask_login import login_required, current_user
from sqlalchemy.dialects.mysql import insert as mysql_insert

from app import db
from app.models import Plant, PlantDailyVolume, UserPlantAccess
from app.decorators import manual_entry_required
from app.services.audit import log_action
from app.services.volume_helpers import recalc_monthly_volumes_batch

_IST = pytz.timezone('Asia/Kolkata')
_logger = logging.getLogger(__name__)

daily_volume_bp = Blueprint("daily_volume", __name__)

MAX_VOLUME = 500_000  # realistic ceiling (CUM); prevents accidental/corrupted data


@daily_volume_bp.route("/manual-entry")
@manual_entry_required
def manual_entry_page():
    """Manual entry page. Admin + manual_entry users only."""
    return render_template("manual_entry.html")


@daily_volume_bp.route("/api/manual-plants")
@manual_entry_required
def api_manual_plants():
    """List plants available to the current user for manual entry."""
    if current_user.role == 'admin' or current_user.manual_entry_all_plants:
        plants = (
            Plant.query
            .filter_by(is_active=True)
            .order_by(Plant.region, Plant.daily_tracker_name)
            .all()
        )
    else:
        accesses = UserPlantAccess.query.filter_by(user_id=current_user.id).all()
        plant_codes = [a.plant_code for a in accesses]
        plants = (
            Plant.query
            .filter(Plant.plant_code.in_(plant_codes), Plant.is_active == True)
            .order_by(Plant.region, Plant.daily_tracker_name)
            .all()
        )
    date_str = request.args.get("date")
    entry_date = None
    if date_str:
        try:
            entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            pass

    result = []
    if entry_date and plants:
        # Batch-fetch volumes (1 query instead of N)
        codes = [p.plant_code for p in plants]
        vols = PlantDailyVolume.query.filter(
            PlantDailyVolume.plant_code.in_(codes),
            PlantDailyVolume.entry_date == entry_date,
        ).all()
        vol_map = {v.plant_code: float(v.volume) for v in vols}
        for p in plants:
            d = p.to_dict()
            d["volume"] = vol_map.get(p.plant_code, 0.0)
            result.append(d)
    else:
        result = [p.to_dict() for p in plants]

    return jsonify({"plants": result})


@daily_volume_bp.route("/api/daily-volume", methods=["POST"])
@manual_entry_required
def api_submit_daily_volume():
    """
    Submit daily volume — single or bulk.
    Admin + manual_entry users only.

    Body: { entries: [{ plant_code, entry_date, volume }, ...] }
    """
    data = request.get_json()
    if not data or "entries" not in data:
        return jsonify({"error": "entries array is required"}), 400

    entries = data["entries"]
    if not isinstance(entries, list):
        return jsonify({"error": "entries must be an array"}), 400
    if len(entries) > 500:
        return jsonify({"error": "Too many entries (max 500 per request)"}), 400

    saved = 0
    errors = []
    months_to_recalc: dict = {}  # { month_start_date: set(plant_codes) }

    for entry in entries:
        plant_code = entry.get("plant_code", "").strip()
        date_str = entry.get("entry_date", "")
        volume = entry.get("volume")

        if not plant_code or not date_str:
            errors.append(f"Missing plant_code or entry_date")
            continue

        try:
            entry_date = datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            errors.append(f"{plant_code}: invalid date format")
            continue

        today = datetime.now(_IST).date()  # IST date, not server-UTC
        if entry_date >= today:
            errors.append(f"{plant_code}: date cannot be today or in the future — today's production is unknown until the day ends")
            continue
        if current_user.role == 'admin':
            if entry_date < today - timedelta(days=30):
                errors.append(f"{plant_code}: can only edit up to 30 days in the past")
                continue
        else:
            if entry_date < today - timedelta(days=3):
                errors.append(f"{plant_code}: can only submit data up to 3 days in the past")
                continue

        try:
            volume = float(volume or 0)
        except (ValueError, TypeError):
            errors.append(f"{plant_code}: invalid volume")
            continue

        if volume < 0:
            errors.append(f"{plant_code}: volume cannot be negative")
            continue

        if volume > MAX_VOLUME:
            errors.append(f"{plant_code}: volume exceeds maximum allowed ({MAX_VOLUME:,})")
            continue

        # Check plant exists and is active
        plant = db.session.get(Plant, plant_code)
        if not plant:
            errors.append(f"{plant_code}: plant not found")
            continue
        if not plant.is_active:
            errors.append(f"{plant_code}: plant is inactive")
            continue

        # Check plant access for non-admin users
        if current_user.role != 'admin' and not current_user.manual_entry_all_plants:
            access = UserPlantAccess.query.filter_by(
                user_id=current_user.id, plant_code=plant_code
            ).first()
            if not access:
                errors.append(f"{plant_code}: access denied")
                continue

        # Atomic upsert — avoids race condition on concurrent submissions
        upsert = mysql_insert(PlantDailyVolume.__table__).values(
            plant_code=plant_code,
            entry_date=entry_date,
            volume=volume,
        ).on_duplicate_key_update(volume=volume)
        db.session.execute(upsert)

        # Track months that need recalculation (done in batch after commit)
        m_start = date(entry_date.year, entry_date.month, 1)
        months_to_recalc.setdefault(m_start, set()).add(plant_code)

        saved += 1

    try:
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        return jsonify({"error": f"Database error: {str(exc)}"}), 500

    # Batch recalculate monthly volumes — far fewer queries than per-entry calls
    recalc_warning = None
    try:
        for m_start, plant_codes in months_to_recalc.items():
            recalc_monthly_volumes_batch(m_start, list(plant_codes))
        db.session.commit()
    except Exception as exc:
        db.session.rollback()
        _logger.error(f"Monthly recalc failed after manual entry: {exc}")
        recalc_warning = "Volumes saved, but monthly totals could not be updated. They will sync on next data entry."

    log_action("manual_entry", {
        "saved": saved,
        "entries": len(entries),
        "date": data["entries"][0].get("entry_date") if entries else None,
    })
    db.session.commit()  # commit the audit log entry

    # If nothing was saved at all, return 400 so the frontend error handler fires
    if saved == 0:
        return jsonify({
            "status": "error",
            "saved": 0,
            "errors": errors,
            "error": errors[0] if errors else "No entries were saved.",
        }), 400

    resp = {"status": "success", "saved": saved, "errors": errors}
    if recalc_warning:
        resp["warning"] = recalc_warning
    return jsonify(resp)


@daily_volume_bp.route("/api/daily-volume/<plant_code>")
@login_required
def api_get_daily_volumes(plant_code):
    """Get daily volumes for a plant. Supports ?days=N (last N days) or ?month=YYYY-MM."""
    days_param = request.args.get("days", type=int)
    if days_param:
        end_date   = date.today()
        start_date = end_date - timedelta(days=days_param - 1)
        volumes = (
            PlantDailyVolume.query
            .filter(
                PlantDailyVolume.plant_code == plant_code,
                PlantDailyVolume.entry_date >= start_date,
                PlantDailyVolume.entry_date <= end_date,
            )
            .order_by(PlantDailyVolume.entry_date.desc())
            .all()
        )
        return jsonify({
            "plant_code": plant_code,
            "volumes": [v.to_dict() for v in volumes],
        })

    month_str = request.args.get("month")  # YYYY-MM format
    if month_str:
        try:
            year, month = month_str.split("-")
            month_start = date(int(year), int(month), 1)
        except (ValueError, IndexError):
            return jsonify({"error": "Invalid month format. Use YYYY-MM"}), 400
    else:
        today = date.today()
        month_start = date(today.year, today.month, 1)

    # Get next month start
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)

    volumes = (
        PlantDailyVolume.query
        .filter(
            PlantDailyVolume.plant_code == plant_code,
            PlantDailyVolume.entry_date >= month_start,
            PlantDailyVolume.entry_date < next_month,
        )
        .order_by(PlantDailyVolume.entry_date)
        .all()
    )

    return jsonify({
        "plant_code": plant_code,
        "month": month_start.isoformat(),
        "volumes": [v.to_dict() for v in volumes],
    })
