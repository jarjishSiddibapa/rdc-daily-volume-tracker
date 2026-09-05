"""ERP sync service — fetches Oracle data and upserts into MySQL."""

import logging
from datetime import date, timedelta, datetime

from sqlalchemy.dialects.mysql import insert as mysql_insert

from app import db
from app.models import Plant, PlantDailyVolume
from app.oracle_service import (
    fetch_erp_daily_invoiced,
    fetch_erp_daily_production,
    fetch_erp_organizations,
)
from app.services.audit import log_action
from app.services.volume_helpers import recalc_monthly_volumes_batch
from app.services.report_generator import invalidate_report_cache

logger = logging.getLogger(__name__)

# ERP plant sync is only allowed from this date onwards
ERP_SYNC_START_DATE = date(2026, 5, 1)


def _sync_erp_organization_master() -> dict:
    """Create newly-discovered ERP plants without changing existing statuses.

    The one-time active-list reconciliation is responsible for establishing the
    approved active/inactive baseline. After that baseline exists, this routine
    preserves every existing status and defaults only genuinely new ERP codes to
    active. Tracker names are also preserved; Oracle name changes update only the
    ERP-name field.
    """
    organizations = fetch_erp_organizations()
    if organizations is None:
        return {
            "available": False,
            "organization_count": 0,
            "new_plant_details": [],
            "erp_names_updated": 0,
        }

    organization_master = {}
    for record in organizations:
        plant_code = str(record.get("organization_code") or "").strip().upper()
        erp_name = str(record.get("organization_name") or "").strip()
        if not plant_code or plant_code in organization_master:
            continue
        organization_master[plant_code] = erp_name

    existing_plants = {
        plant.plant_code.strip().upper(): plant
        for plant in Plant.query.filter(
            Plant.plant_code.in_(list(organization_master))
        ).all()
    }
    new_plant_details = []
    erp_names_updated = 0

    for plant_code, erp_name in organization_master.items():
        plant = existing_plants.get(plant_code)
        if plant is None:
            plant = Plant(
                plant_code=plant_code,
                erp_name=erp_name,
                daily_tracker_name=erp_name or plant_code,
                region="",
                is_active=True,
                is_manual_entry=False,
            )
            db.session.add(plant)
            new_plant_details.append({"plant_code": plant_code, "erp_name": erp_name})
            logger.info("Discovered new active ERP plant: %s (%s)", plant_code, erp_name)
        elif erp_name and plant.erp_name != erp_name:
            plant.erp_name = erp_name
            erp_names_updated += 1

    # Make new parent rows visible to the Core daily-volume upserts below.
    db.session.flush()
    return {
        "available": True,
        "organization_count": len(organization_master),
        "new_plant_details": new_plant_details,
        "erp_names_updated": erp_names_updated,
    }


def _get_months_to_sync() -> list[tuple[date, date]]:
    """
    Return a list of (month_start, month_end) tuples to sync.

    Always syncs:
      - Previous month (full) — ensures missed end-of-month data is always caught up
      - Current month (up to yesterday)
    """
    today = date.today()
    yesterday = today - timedelta(days=1)

    # Current month
    cur_month_start = date(today.year, today.month, 1)

    # Previous month
    prev_month_end = cur_month_start - timedelta(days=1)  # last day of prev month
    prev_month_start = date(prev_month_end.year, prev_month_end.month, 1)

    months = []

    # Previous month (full month) — always synced on every run
    months.append((prev_month_start, prev_month_end))

    # Current month (up to yesterday, only if we're past the 1st)
    if yesterday >= cur_month_start:
        months.append((cur_month_start, yesterday))

    return months


def sync_erp_data() -> dict:
    """
    Fetch production data from ERP and store in MySQL.

    Steps:
      1. Discover new plants from the ERP organization master
      2. Fetch daily breakdown for previous + current month
      3. Recalculate monthly volumes from daily entries (single source of truth)

    Returns a dict with status info.
    """
    months_to_sync = _get_months_to_sync()

    synced_daily = 0
    synced_monthly = 0
    skipped = 0
    new_plants = 0
    new_plant_details = []
    organization_master_count = 0
    erp_names_updated = 0
    errors = []
    months_synced = []
    all_synced_plants = {}  # { month_start: set(plant_codes) }

    # Discover every eligible ERP organization, including plants that have not
    # produced a batch yet. Existing active/inactive choices are never changed.
    try:
        master_result = _sync_erp_organization_master()
    except Exception as exc:
        db.session.rollback()
        return {"status": "error", "message": f"ERP organization sync failed: {str(exc)}"}

    if master_result["available"]:
        new_plant_details.extend(master_result["new_plant_details"])
        new_plants += len(master_result["new_plant_details"])
        organization_master_count = master_result["organization_count"]
        erp_names_updated = master_result["erp_names_updated"]
    else:
        errors.append("Oracle organization master unavailable")

    # Get manual-entry plants to skip them after master discovery.
    manual_plants = {
        p.plant_code.strip().upper()
        for p in Plant.query.filter_by(is_manual_entry=True).all()
    }

    for month_start, month_end in months_to_sync:
        logger.info(f"Syncing ERP daily data: {month_start} → {month_end}")

        # ── Fetch daily breakdown from Oracle ────────────────────────────
        daily_data = fetch_erp_daily_production(
            month_start=month_start,
            month_end=month_end,
        )

        if daily_data is None:
            errors.append(f"Oracle unreachable for {month_start} → {month_end}")
            continue

        # ── Fetch daily invoiced quantities for the same window ──────────
        invoiced_data = fetch_erp_daily_invoiced(
            month_start=month_start,
            month_end=month_end,
        )
        inv_lookup: dict = {}
        inv_data_available = invoiced_data is not None
        if inv_data_available:
            for ir in invoiced_data:
                key = (
                    ir.get("organization_code", "").strip().upper(),
                    ir.get("inv_date", ""),
                )
                inv_lookup[key] = float(ir.get("invoiced_qty") or 0)
        else:
            logger.warning(f"Invoiced data unavailable for {month_start} → {month_end}; preserving existing values")

        synced_plants_this_month = set()
        months_synced.append(month_start.isoformat())

        # ── Upsert all daily volumes ─────────────────────────────────────
        for record in daily_data:
            plant_code = record.get("organization_code", "").strip().upper()
            erp_name = record.get("organization_name", "").strip()
            prod_date_str = record.get("prod_date", "").strip()
            daily_volume = float(record.get("daily_volume", 0) or 0)

            if not plant_code or not prod_date_str:
                continue

            # Skip manual-entry plants
            if plant_code in manual_plants:
                skipped += 1
                continue

            # Skip zero-volume ERP records — 0 from Oracle means no invoice data
            # for that date, not genuine zero production. Preserves manual entries.
            if daily_volume == 0:
                skipped += 1
                continue

            # Parse the date
            try:
                entry_date = datetime.strptime(prod_date_str, "%Y-%m-%d").date()
            except ValueError:
                errors.append(f"{plant_code}: invalid date {prod_date_str}")
                continue

            # Check if plant exists; auto-create if new
            plant = db.session.get(Plant, plant_code)
            if not plant:
                if date.today() >= ERP_SYNC_START_DATE:
                    plant = Plant(
                        plant_code=plant_code,
                        erp_name=erp_name,
                        daily_tracker_name=erp_name,  # default tracker name = ERP name
                        region="",
                        is_active=True,   # immediately visible in reports; admin can deactivate if needed
                        is_manual_entry=False,
                    )
                    db.session.add(plant)
                    # Flush now — the daily-volume upsert below is a raw Core
                    # INSERT executed via session.execute(), which does not
                    # reliably autoflush pending ORM adds first. Without this,
                    # the very first daily-volume row for a brand-new plant
                    # can fail its FK check and be silently dropped.
                    db.session.flush()
                    new_plants += 1
                    new_plant_details.append({"plant_code": plant_code, "erp_name": erp_name})
                    logger.info(f"Auto-created new plant from ERP: {plant_code} ({erp_name}) — active")
                else:
                    continue

            try:
                inv_qty = inv_lookup.get((plant_code, prod_date_str), 0.0)
                update_fields = {"volume": daily_volume}
                if inv_data_available:
                    update_fields["invoiced_qty"] = inv_qty
                # Atomic upsert — safe under concurrent ERP syncs
                upsert = mysql_insert(PlantDailyVolume.__table__).values(
                    plant_code=plant_code,
                    entry_date=entry_date,
                    volume=daily_volume,
                    invoiced_qty=inv_qty,
                ).on_duplicate_key_update(**update_fields)
                db.session.execute(upsert)

                synced_daily += 1
                synced_plants_this_month.add(plant_code)
            except Exception as exc:
                errors.append(f"{plant_code} ({prod_date_str}): {str(exc)}")
                logger.error(f"Error syncing daily for {plant_code} on {prod_date_str}: {exc}")

        all_synced_plants[month_start] = synced_plants_this_month

    # ── Recalculate monthly volumes from daily entries (batch: ~3 queries/month) ─
    for m_start, plant_codes in all_synced_plants.items():
        try:
            recalc_monthly_volumes_batch(m_start, list(plant_codes))
            synced_monthly += len(plant_codes)
        except Exception as exc:
            errors.append(f"monthly recalc {m_start}: {str(exc)}")
            logger.error(f"Error in batch monthly recalc for {m_start}: {exc}")

    # ── Commit everything ────────────────────────────────────────────────
    try:
        db.session.commit()
        invalidate_report_cache()
    except Exception as exc:
        db.session.rollback()
        return {"status": "error", "message": f"Database commit failed: {str(exc)}"}

    log_action("erp_sync", {
        "synced_daily": synced_daily,
        "synced_monthly": synced_monthly,
        "new_plants": new_plants,
        "new_plant_details": new_plant_details,
        "organization_master_count": organization_master_count,
        "erp_names_updated": erp_names_updated,
        "months": months_synced,
        "errors": errors,
    })
    db.session.commit()

    return {
        "status": "success",
        "synced_daily": synced_daily,
        "synced_monthly": synced_monthly,
        "skipped": skipped,
        "new_plants": new_plants,
        "new_plant_details": new_plant_details,
        "organization_master_count": organization_master_count,
        "erp_names_updated": erp_names_updated,
        "errors": errors,
        "months": months_synced,
    }
