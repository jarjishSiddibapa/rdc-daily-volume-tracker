"""Volume helpers — shared utilities for managing volume calculations."""

from datetime import date
from typing import List
from sqlalchemy import func

from app import db
from app.models import PlantDailyVolume, PlantMonthlyVolume


def recalc_monthly_volume(plant_code: str, month_start: date):
    """
    Recalculate the monthly total volume for a plant from its daily entries.

    This is the single source of truth: monthly volume = SUM(daily entries).
    Called after any daily volume insert/update (manual entry, ERP sync, etc.).
    """
    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)

    total = (
        db.session.query(func.sum(PlantDailyVolume.volume))
        .filter(
            PlantDailyVolume.plant_code == plant_code,
            PlantDailyVolume.entry_date >= month_start,
            PlantDailyVolume.entry_date < next_month,
        )
        .scalar()
    ) or 0

    monthly = PlantMonthlyVolume.query.filter_by(
        plant_code=plant_code, month_date=month_start
    ).first()

    if monthly:
        monthly.total_actual_volume = float(total)
    else:
        monthly = PlantMonthlyVolume(
            plant_code=plant_code,
            month_date=month_start,
            total_actual_volume=float(total),
        )
        db.session.add(monthly)


def recalc_monthly_volumes_batch(month_start: date, plant_codes: List[str]):
    """
    Recalculate monthly total volumes for multiple plants in ~3 queries total.

    Much more efficient than calling recalc_monthly_volume() per plant, especially
    during ERP sync (100+ plants) or bulk manual entry submissions.
    """
    if not plant_codes:
        return

    if month_start.month == 12:
        next_month = date(month_start.year + 1, 1, 1)
    else:
        next_month = date(month_start.year, month_start.month + 1, 1)

    # 1 query: aggregate daily volumes for all plants at once
    rows = (
        db.session.query(
            PlantDailyVolume.plant_code,
            func.sum(PlantDailyVolume.volume).label("total"),
        )
        .filter(
            PlantDailyVolume.plant_code.in_(plant_codes),
            PlantDailyVolume.entry_date >= month_start,
            PlantDailyVolume.entry_date < next_month,
        )
        .group_by(PlantDailyVolume.plant_code)
        .all()
    )
    totals = {r.plant_code: float(r.total) for r in rows}

    # 1 query: fetch all existing monthly rows for these plants
    existing = {
        r.plant_code: r
        for r in PlantMonthlyVolume.query.filter(
            PlantMonthlyVolume.plant_code.in_(plant_codes),
            PlantMonthlyVolume.month_date == month_start,
        ).all()
    }

    for pc in plant_codes:
        total = totals.get(pc, 0.0)
        if pc in existing:
            existing[pc].total_actual_volume = total
        else:
            db.session.add(PlantMonthlyVolume(
                plant_code=pc,
                month_date=month_start,
                total_actual_volume=total,
            ))
