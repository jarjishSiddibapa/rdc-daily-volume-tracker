"""Reconcile the plant table from an approved active-plant workbook."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from urllib.parse import quote_plus

from flask import Flask


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# A maintenance command must never start the in-process scheduler.
os.environ["SCHEDULER_ENABLED"] = "false"

from app import db  # noqa: E402
from app.oracle_service import fetch_erp_organizations  # noqa: E402
from app.services.audit import log_action  # noqa: E402
from app.services.plant_master import (  # noqa: E402
    load_active_plant_workbook,
    normalize_erp_organizations,
    reconcile_plant_master,
    validate_active_plants_against_erp,
)
from app.services.report_generator import invalidate_report_cache  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Set the approved active plants and tracker names from Excel, mark all "
            "other existing plants inactive, and record the current ERP master."
        )
    )
    parser.add_argument("workbook", type=Path, help="Path to the approved .xlsx file")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Commit the reconciliation. Without this flag the command is read-only.",
    )
    return parser.parse_args()


def create_maintenance_app() -> Flask:
    """Create a database-only app without startup seeds or background jobs."""
    app = Flask("plant_master_reconciliation")
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
    args = parse_args()
    try:
        active_plants = load_active_plant_workbook(args.workbook)
    except ValueError as exc:
        print(f"Workbook validation failed: {exc}", file=sys.stderr)
        return 2

    erp_rows = fetch_erp_organizations()
    if erp_rows is None:
        print("Oracle organization master could not be read; nothing was changed.", file=sys.stderr)
        return 3

    try:
        erp_organizations = normalize_erp_organizations(erp_rows)
        name_differences = validate_active_plants_against_erp(
            active_plants, erp_organizations
        )
    except ValueError as exc:
        print(f"ERP validation failed: {exc}", file=sys.stderr)
        return 4

    app = create_maintenance_app()
    with app.app_context():
        try:
            summary = reconcile_plant_master(
                active_plants,
                erp_organizations,
                apply_changes=args.apply,
            )
            summary["erp_name_differences"] = name_differences

            if args.apply:
                log_action("plant_master_reconcile", summary)
                db.session.commit()
                invalidate_report_cache()
            else:
                db.session.rollback()
        except Exception as exc:
            db.session.rollback()
            print(f"Reconciliation failed; no changes were committed: {exc}", file=sys.stderr)
            return 5

    print(json.dumps(summary, indent=2, ensure_ascii=False))
    print("Changes committed." if args.apply else "Dry run only; no changes committed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
