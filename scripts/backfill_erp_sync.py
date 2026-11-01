"""Re-sync ERP production and invoiced quantities for a range of past months."""

from __future__ import annotations

import argparse
import calendar
import os
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

from flask import Flask


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# A maintenance command must never start the in-process scheduler.
os.environ["SCHEDULER_ENABLED"] = "false"

from app import db  # noqa: E402
from app.services.erp_sync import sync_erp_data  # noqa: E402


def parse_month(value: str) -> date:
    try:
        return datetime.strptime(value, "%Y-%m").date()
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} is not a month in YYYY-MM form")


def month_ranges(first: date, last: date) -> list[tuple[date, date]]:
    """(month_start, month_end) pairs from first to last month, capped at yesterday."""
    yesterday = date.today() - timedelta(days=1)
    ranges = []
    year, month = first.year, first.month
    while (year, month) <= (last.year, last.month):
        start = date(year, month, 1)
        end = min(date(year, month, calendar.monthrange(year, month)[1]), yesterday)
        if end >= start:
            ranges.append((start, end))
        year, month = (year + 1, 1) if month == 12 else (year, month + 1)
    return ranges


def create_maintenance_app() -> Flask:
    """Create a database-only app without startup seeds or background jobs."""
    app = Flask("erp_backfill")
    app.config.update(
        SQLALCHEMY_DATABASE_URI=(
            f"mysql+pymysql://{os.getenv('MYSQL_USER', 'root')}:"
            f"{quote_plus(os.getenv('MYSQL_PASSWORD', ''))}@"
            f"{os.getenv('MYSQL_HOST', 'localhost')}:"
            f"{os.getenv('MYSQL_PORT', '3306')}/"
            f"{os.getenv('MYSQL_DB', 'daily_volume_tracker')}"
        ),
        SQLALCHEMY_TRACK_MODIFICATIONS=False,
        SQLALCHEMY_ENGINE_OPTIONS={"pool_pre_ping": True},
    )
    db.init_app(app)
    return app


def main() -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Re-run the ERP sync for past months. Fills missing days (including "
            "invoice-only days) and invoiced quantities; ERP volumes overwrite "
            "stored volumes for days the ERP reports production."
        )
    )
    parser.add_argument("start", type=parse_month, help="First month, YYYY-MM")
    parser.add_argument("end", type=parse_month, help="Last month, YYYY-MM")
    args = parser.parse_args()

    if args.end < args.start:
        print("End month is before start month.", file=sys.stderr)
        return 2

    ranges = month_ranges(args.start, args.end)
    if not ranges:
        print("No completed days in that range.", file=sys.stderr)
        return 2

    app = create_maintenance_app()
    with app.app_context():
        result = sync_erp_data(months=ranges)

    print(
        f"status={result['status']} months={result.get('months')} "
        f"synced_daily={result.get('synced_daily')} "
        f"synced_invoice_only={result.get('synced_invoice_only')}"
    )
    if result.get("errors") or result["status"] != "success":
        print(f"errors: {result.get('errors') or result.get('message')}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
