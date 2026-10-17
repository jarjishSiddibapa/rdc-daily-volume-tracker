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
    RECENT_PRODUCTION_DAYS,
    find_recent_production,
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
    parser.add_argument(
        "--yes",
        action="store_true",
        help="With --apply, skip the confirmation prompt (for non-interactive use).",
    )
    return parser.parse_args()


def print_impact(preview: dict, at_risk: dict) -> None:
    """Show what the reconciliation will change before anything is committed."""
    print("This reconciliation will:")
    print(f"  activate {len(preview['activated'])} existing plant(s)")
    print(f"  deactivate {len(preview['deactivated'])} existing plant(s)")
    print(f"  create {len(preview['created_active'])} plant(s) as ACTIVE")
    print(f"  create {len(preview['created_inactive'])} plant(s) as INACTIVE")
    print(f"  update {len(preview['tracker_names_updated'])} tracker name(s)")

    if at_risk:
        print(
            f"\nWARNING: {len(at_risk)} plant(s) that would be DEACTIVATED produced "
            f"within the last {RECENT_PRODUCTION_DAYS} days and would disappear from reports:"
        )
        for code, info in sorted(at_risk.items()):
            print(
                f"  {code}: {info['production_days']} production day(s), "
                f"last on {info['last_production']}"
            )
    print()


def confirm_apply(skip_prompt: bool) -> bool:
    """Require an explicit confirmation before committing changes."""
    if skip_prompt:
        return True
    if not sys.stdin.isatty():
        print(
            "Refusing to --apply without an interactive terminal. "
            "Re-run in a terminal, or add --yes to confirm.",
            file=sys.stderr,
        )
        return False
    try:
        return input("Type APPLY to commit these changes: ").strip() == "APPLY"
    except EOFError:
        # Input closed (for example a redirected or detached console).
        return False


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
            # Always compute a read-only preview first so the impact is visible
            # (and confirmed) before anything is changed.
            summary = reconcile_plant_master(
                active_plants,
                erp_organizations,
                apply_changes=False,
            )
            at_risk = find_recent_production(summary["deactivated"])
            print_impact(summary, at_risk)

            if args.apply:
                if not confirm_apply(args.yes):
                    db.session.rollback()
                    print("Cancelled; no changes committed.", file=sys.stderr)
                    return 6
                summary = reconcile_plant_master(
                    active_plants,
                    erp_organizations,
                    apply_changes=True,
                )

            summary["erp_name_differences"] = name_differences
            summary["deactivated_with_recent_production"] = at_risk

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
