"""
Report generation engine — produces the exact tabular report format.

Computes: Daily Volume, Daily Avg, Req Vol/day, MTD, Extrapolated Vol,
Budget/Target, % Extrap vs Budget, Last Month Vol, % vs Last Month,
Last Year Same Month Vol, % vs Last Year.

Groups plants by region with subtotals and a Company Total row.
"""

import logging
import time as _time
from datetime import date, timedelta
from calendar import monthrange
from decimal import Decimal

from sqlalchemy import func

from app import db
from app.models import Plant, PlantDailyVolume, PlantMonthlyVolume, PlantMonthlyTarget

logger = logging.getLogger(__name__)

# ── Region display order ──────────────────────────────────────────────────────
# Hardcoded fallback; overridden by DB at runtime via get_region_order()
REGION_ORDER = [
    "DELHI NCR", "JAMMU", "PUNJAB", "UTTARAKHAND", "UTTAR PRADESH",
    "RAJASTHAN", "ASSAM", "KOLKATA", "WEST BENGAL", "BIHAR",
    "JHARKHAND", "ODISHA", "HYDERABAD", "BANGALORE", "CHENNAI",
    "COIMBATORE & TRICHY", "KERALA", "PUNE", "MUMBAI", "NAGPUR",
    "Chh. Sambhaji Nagar", "GOA", "GUJRAT", "CHHATISGARH", "MADHYA PRADESH",
]


_region_cache: tuple = (0.0, None)  # (monotonic_timestamp, list_of_region_names)
_REGION_CACHE_TTL = 3600  # 1 hour


def invalidate_region_cache():
    """Force the next get_region_order() call to re-query the DB.
    Call this whenever regions are created, updated, deleted, or reordered.
    """
    global _region_cache
    _region_cache = (0.0, None)


def get_region_order():
    """Load region order from DB; fall back to hardcoded list. Cached for 1 hour."""
    global _region_cache
    ts, val = _region_cache
    if val is not None and (_time.monotonic() - ts) < _REGION_CACHE_TTL:
        return val
    try:
        from app.models import Region
        regions = Region.query.order_by(Region.display_order, Region.name).all()
        if regions:
            result = [r.name for r in regions]
            _region_cache = (_time.monotonic(), result)
            return result
    except Exception:
        pass
    return REGION_ORDER


def _get_region_labels() -> dict:
    """Build region label map (A, B, C...) from the current live region order.

    Called inside generate_report() so it always reflects DB order, not
    the hardcoded REGION_ORDER fallback.
    For >26 regions, labels continue as AA, AB, etc.
    """
    from openpyxl.utils import get_column_letter
    order = get_region_order()
    return {name: get_column_letter(i + 1) for i, name in enumerate(order)}


def _safe_float(val) -> float:
    """Convert any numeric/Decimal/None to float."""
    if val is None:
        return 0.0
    if isinstance(val, Decimal):
        return float(val)
    return float(val)


def _combined_name(plant) -> str:
    """Combine tracker name and ERP name for display.
    e.g. 'NCR-Faridabad (B11)' or just the one that exists.
    """
    t = (plant.daily_tracker_name or "").strip()
    e = (plant.erp_name or "").strip()
    if t and e and t != e:
        return f"{t} ({e})"
    return t or e or plant.plant_code


def _pct(numerator: float, denominator: float) -> str:
    """Compute percentage string, handle division by zero."""
    if denominator == 0:
        return "100%" if numerator > 0 else "0%"
    return f"{round((numerator / denominator) * 100)}%"


def _pct_variation(current: float, previous: float) -> str:
    """Compute % variation = (current - previous) / previous."""
    if previous == 0:
        return "100%" if current > 0 else "0%"
    return f"{round(((current - previous) / previous) * 100)}%"


def generate_report(report_date: date = None) -> dict:
    """
    Generate the full report for a given date.

    Args:
        report_date: The date to generate the report for (defaults to today).

    Returns:
        dict with keys: meta, regions (list of region groups), company_total
    """
    if report_date is None:
        report_date = date.today()

    # Build region label map fresh from DB order every report call
    region_labels = _get_region_labels()

    # ── Date calculations ──────────────────────────────────────────────────
    yesterday = report_date - timedelta(days=1)

    # If today is the 1st of a new month, report in the context of yesterday's
    # month. On June 1, yesterday is May 31 — the meaningful picture is still
    # May's MTD/targets/extrapolation. June's tracking starts from June 2
    # once actual June data exists.
    effective_date = yesterday if report_date.day == 1 else report_date

    month_start = date(effective_date.year, effective_date.month, 1)
    days_in_month = monthrange(effective_date.year, effective_date.month)[1]

    # MTD days = days elapsed in the reporting month up to (not including) report_date.
    # On the 1st (effective_date = yesterday = last day of prev month) this equals
    # the full month length, leaving balance_days = 0 (month is complete).
    mtd_days = (report_date - month_start).days
    if mtd_days <= 0:
        mtd_days = 1  # safety guard, should not trigger with the effective_date logic
    balance_days = max(days_in_month - mtd_days, 0)

    # Last month
    if month_start.month == 1:
        last_month_start = date(month_start.year - 1, 12, 1)
    else:
        last_month_start = date(month_start.year, month_start.month - 1, 1)

    # Last year same month
    last_year_month_start = date(month_start.year - 1, month_start.month, 1)

    # ── Fetch all active plants ────────────────────────────────────────────
    plants = Plant.query.filter_by(is_active=True).order_by(Plant.region, Plant.display_order, Plant.daily_tracker_name).all()

    # ── Pre-fetch data in bulk for performance ─────────────────────────────

    # Yesterday's daily volumes + invoiced quantity
    _yday_rows = PlantDailyVolume.query.filter_by(entry_date=yesterday).all()
    yesterday_vols = {r.plant_code: _safe_float(r.volume) for r in _yday_rows}
    yesterday_inv  = {r.plant_code: _safe_float(r.invoiced_qty) for r in _yday_rows}

    # MTD volumes (sum of daily volumes for current month)
    mtd_result = (
        db.session.query(
            PlantDailyVolume.plant_code,
            func.sum(PlantDailyVolume.volume).label("mtd_vol"),
        )
        .filter(
            PlantDailyVolume.entry_date >= month_start,
            PlantDailyVolume.entry_date < report_date,
        )
        .group_by(PlantDailyVolume.plant_code)
        .all()
    )
    mtd_vols = {r.plant_code: _safe_float(r.mtd_vol) for r in mtd_result}

    # Last month + last year volumes — combined into a single query
    hist_rows = PlantMonthlyVolume.query.filter(
        PlantMonthlyVolume.month_date.in_([last_month_start, last_year_month_start])
    ).all()
    last_month_vols = {
        r.plant_code: _safe_float(r.total_actual_volume)
        for r in hist_rows if r.month_date == last_month_start
    }
    last_year_vols = {
        r.plant_code: _safe_float(r.total_actual_volume)
        for r in hist_rows if r.month_date == last_year_month_start
    }

    # Monthly targets for current month
    targets = {
        r.plant_code: _safe_float(r.target_volume)
        for r in PlantMonthlyTarget.query.filter_by(month_date=month_start).all()
    }

    # ── Build plant rows ───────────────────────────────────────────────────
    plant_rows = []
    for plant in plants:
        pc = plant.plant_code
        daily_vol = yesterday_vols.get(pc, 0.0)
        mtd_vol = mtd_vols.get(pc, 0.0)
        target = targets.get(pc, 0.0)
        last_month = last_month_vols.get(pc, 0.0)
        last_year = last_year_vols.get(pc, 0.0)

        daily_avg = round(mtd_vol / mtd_days, 2) if mtd_days > 0 else 0.0
        req_vol_day = round((target - mtd_vol) / balance_days, 2) if balance_days > 0 else 0.0
        extrapolated = round(daily_avg * days_in_month, 2)

        pct_extrap_vs_budget = _pct(extrapolated, target)
        pct_vs_last_month = _pct_variation(extrapolated, last_month)
        pct_vs_last_year = _pct_variation(extrapolated, last_year)

        plant_rows.append({
            "plant_code": pc,
            "plant_name": _combined_name(plant),
            "region": plant.region,
            "is_manual_entry": plant.is_manual_entry,
            "daily_volume": round(daily_vol, 2),
            "invoiced_qty": round(yesterday_inv.get(pc, 0.0), 2),
            "daily_avg": round(daily_avg, 2),
            "req_vol_day": round(req_vol_day, 2),
            "mtd_volume": round(mtd_vol, 2),
            "extrapolated": round(extrapolated, 2),
            "target": round(target, 2),
            "pct_extrap_vs_budget": pct_extrap_vs_budget,
            "last_month": round(last_month, 2),
            "pct_vs_last_month": pct_vs_last_month,
            "last_year": round(last_year, 2),
            "pct_vs_last_year": pct_vs_last_year,
        })

    # ── Group by region ────────────────────────────────────────────────────
    regions = {}
    for row in plant_rows:
        region = row["region"] or "Unassigned"
        if region not in regions:
            regions[region] = {"name": region, "plants": [], "subtotal": {}}
        regions[region]["plants"].append(row)

    # ── Compute region subtotals ───────────────────────────────────────────
    for region_name, region_data in regions.items():
        # Unassigned plants are shown but have no subtotal row
        if region_name == "Unassigned":
            region_data["subtotal"] = None
            continue

        plants_in_region = region_data["plants"]
        total_daily = sum(p["daily_volume"] for p in plants_in_region)
        total_invoiced = sum(p["invoiced_qty"] for p in plants_in_region)
        total_mtd = sum(p["mtd_volume"] for p in plants_in_region)
        total_target = sum(p["target"] for p in plants_in_region)
        total_last_month = sum(p["last_month"] for p in plants_in_region)
        total_last_year = sum(p["last_year"] for p in plants_in_region)

        total_daily_avg = round(total_mtd / mtd_days, 2) if mtd_days > 0 else 0.0
        total_req_vol = round((total_target - total_mtd) / balance_days, 2) if balance_days > 0 else 0.0
        total_extrapolated = round(total_daily_avg * days_in_month, 2)

        region_data["subtotal"] = {
            "label": region_labels.get(region_name, ""),
            "region_name": region_name,
            "daily_volume": round(total_daily, 2),
            "invoiced_qty": round(total_invoiced, 2),
            "daily_avg": round(total_daily_avg, 2),
            "req_vol_day": round(total_req_vol, 2),
            "mtd_volume": round(total_mtd, 2),
            "extrapolated": round(total_extrapolated, 2),
            "target": round(total_target, 2),
            "pct_extrap_vs_budget": _pct(total_extrapolated, total_target),
            "last_month": round(total_last_month, 2),
            "pct_vs_last_month": _pct_variation(total_extrapolated, total_last_month),
            "last_year": round(total_last_year, 2),
            "pct_vs_last_year": _pct_variation(total_extrapolated, total_last_year),
        }

    # ── Sort regions by defined order ──────────────────────────────────────
    region_order = get_region_order()
    ordered_regions = []
    for region_name in region_order:
        if region_name in regions:
            ordered_regions.append(regions.pop(region_name))
    # Add any regions not in the predefined order (except Unassigned)
    for region_name, region_data in list(regions.items()):
        if region_name != "Unassigned":
            ordered_regions.append(region_data)
    # Unassigned always goes last
    if "Unassigned" in regions:
        ordered_regions.append(regions["Unassigned"])

    # ── Company total (all active plants, including Unassigned) ──────────
    total_daily = sum(p["daily_volume"] for p in plant_rows)
    total_invoiced = sum(p["invoiced_qty"] for p in plant_rows)
    total_mtd = sum(p["mtd_volume"] for p in plant_rows)
    total_target = sum(p["target"] for p in plant_rows)
    total_last_month = sum(p["last_month"] for p in plant_rows)
    total_last_year = sum(p["last_year"] for p in plant_rows)

    total_daily_avg = round(total_mtd / mtd_days, 2) if mtd_days > 0 else 0.0
    total_req_vol = round((total_target - total_mtd) / balance_days, 2) if balance_days > 0 else 0.0
    total_extrapolated = round(total_daily_avg * days_in_month, 2)

    company_total = {
        "label": "Z",
        "region_name": "COMPANY TOTAL",
        "daily_volume": round(total_daily, 2),
        "invoiced_qty": round(total_invoiced, 2),
        "daily_avg": round(total_daily_avg, 2),
        "req_vol_day": round(total_req_vol, 2),
        "mtd_volume": round(total_mtd, 2),
        "extrapolated": round(total_extrapolated, 2),
        "target": round(total_target, 2),
        "pct_extrap_vs_budget": _pct(total_extrapolated, total_target),
        "last_month": round(total_last_month, 2),
        "pct_vs_last_month": _pct_variation(total_extrapolated, total_last_month),
        "last_year": round(total_last_year, 2),
        "pct_vs_last_year": _pct_variation(total_extrapolated, total_last_year),
    }

    # ── Metadata ───────────────────────────────────────────────────────────
    active_plants = len(plant_rows)
    vol_per_plant = round(total_daily / active_plants, 2) if active_plants > 0 else 0.0

    meta = {
        "report_date": report_date.isoformat(),
        "yesterday": yesterday.isoformat(),
        "month_start": month_start.isoformat(),
        "month_end": date(effective_date.year, effective_date.month, days_in_month).isoformat(),
        "days_in_month": days_in_month,
        "mtd_days": mtd_days,
        "balance_days": balance_days,
        "active_plants": active_plants,
        "vol_per_plant": vol_per_plant,
        "summary": (
            f"Volume of {yesterday.strftime('%d.%m.%y')} was "
            f"{round(total_daily):,} CUM, MTD Volume is "
            f"{round(total_mtd):,} CUM and Extrapolated Volume will be "
            f"{round(total_extrapolated):,} CUM, against target of "
            f"{round(total_target):,} CUM ({company_total['pct_extrap_vs_budget']} "
            f"Extrapolation v/s Target, Last Month v/s Extrapolation {company_total['pct_vs_last_month']} "
            f"and Last Year v/s Extrapolation {company_total['pct_vs_last_year']})"
        ),
    }

    return {
        "meta": meta,
        "regions": ordered_regions,
        "company_total": company_total,
    }
