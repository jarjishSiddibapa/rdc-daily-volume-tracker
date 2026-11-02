import json
from datetime import date, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from flask import Flask
from openpyxl import Workbook

from app import db
from app.models import AuditLog, Plant, PlantDailyVolume
from app.services.erp_sync import (
    _activate_or_report_inactive_producing,
    _sync_erp_organization_master,
)
from app.services.plant_master import (
    ActivePlantRecord,
    find_recent_production,
    load_active_plant_workbook,
    reconcile_plant_master,
)


class PlantMasterTests(TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = Flask(__name__)
        cls.app.config.update(
            SQLALCHEMY_DATABASE_URI="sqlite://",
            SQLALCHEMY_TRACK_MODIFICATIONS=False,
        )
        db.init_app(cls.app)

    def setUp(self):
        self.context = self.app.app_context()
        self.context.push()
        db.create_all()

    def tearDown(self):
        db.session.remove()
        db.drop_all()
        self.context.pop()

    def test_workbook_loader_matches_by_code_and_rejects_duplicates(self):
        with TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "plants.xlsx"
            workbook = Workbook()
            sheet = workbook.active
            sheet.title = "Updated Plant Name"
            sheet.append([
                "S. No",
                "ERP Name (key)",
                "Org Code",
                "Display Name (Tracker Name)",
            ])
            sheet.append([1, "ERP Alpha", " a1 ", "Tracker Alpha"])
            workbook.save(path)

            records = load_active_plant_workbook(path)
            self.assertEqual(set(records), {"A1"})
            self.assertEqual(records["A1"].tracker_name, "Tracker Alpha")

            sheet.append([2, "ERP Alpha Again", "A1", "Duplicate"])
            workbook.save(path)
            with self.assertRaisesRegex(ValueError, "Duplicate organization code A1"):
                load_active_plant_workbook(path)

    def test_baseline_reconciliation_sets_exact_active_list(self):
        db.session.add_all([
            Plant(
                plant_code="A1",
                daily_tracker_name="Old Alpha",
                erp_name="ERP Alpha",
                region="North",
                is_active=False,
                is_manual_entry=False,
            ),
            Plant(
                plant_code="B1",
                daily_tracker_name="Tracker Beta",
                erp_name="ERP Beta",
                region="South",
                is_active=True,
                is_manual_entry=True,
            ),
            Plant(
                plant_code="E1",
                daily_tracker_name="Old extra",
                erp_name="Old extra",
                region="",
                is_active=True,
                is_manual_entry=False,
            ),
        ])
        db.session.commit()

        active = {
            "A1": ActivePlantRecord("A1", "ERP Alpha", "Tracker Alpha", 2),
            "C1": ActivePlantRecord("C1", "ERP Gamma", "Tracker Gamma", 3),
        }
        erp = {"A1": "ERP Alpha", "B1": "ERP Beta", "C1": "ERP Gamma", "D1": "ERP Delta"}

        preview = reconcile_plant_master(active, erp, apply_changes=False)
        self.assertEqual(preview["activated"], ["A1"])
        self.assertEqual(preview["deactivated"], ["B1", "E1"])
        self.assertEqual(preview["created_active"], ["C1"])
        self.assertEqual(preview["created_inactive"], ["D1"])
        self.assertFalse(db.session.get(Plant, "A1").is_active)

        applied = reconcile_plant_master(active, erp, apply_changes=True)
        db.session.commit()
        self.assertEqual(applied["tracker_names_updated"], ["A1"])
        self.assertTrue(db.session.get(Plant, "A1").is_active)
        self.assertFalse(db.session.get(Plant, "B1").is_active)
        self.assertFalse(db.session.get(Plant, "E1").is_active)
        self.assertTrue(db.session.get(Plant, "C1").is_active)
        self.assertFalse(db.session.get(Plant, "D1").is_active)
        self.assertTrue(db.session.get(Plant, "B1").is_manual_entry)

    def test_recent_production_flags_only_plants_that_recently_produced(self):
        today = date.today()
        db.session.add_all([
            Plant(plant_code="P1", daily_tracker_name="Producing", erp_name="P1", is_active=True),
            Plant(plant_code="P2", daily_tracker_name="Stale", erp_name="P2", is_active=True),
            Plant(plant_code="P3", daily_tracker_name="Zero only", erp_name="P3", is_active=True),
            Plant(plant_code="P4", daily_tracker_name="Never", erp_name="P4", is_active=True),
        ])
        db.session.commit()
        db.session.add_all([
            # Explicit ids: SQLite does not auto-number BigInteger primary keys.
            PlantDailyVolume(id=1, plant_code="P1", entry_date=today - timedelta(days=1), volume=120),
            PlantDailyVolume(id=2, plant_code="P1", entry_date=today - timedelta(days=3), volume=80),
            PlantDailyVolume(id=3, plant_code="P2", entry_date=today - timedelta(days=90), volume=50),
            PlantDailyVolume(id=4, plant_code="P3", entry_date=today - timedelta(days=1), volume=0),
        ])
        db.session.commit()

        result = find_recent_production(["P1", "P2", "P3", "P4"])

        self.assertEqual(set(result), {"P1"})
        self.assertEqual(result["P1"]["production_days"], 2)
        self.assertEqual(
            result["P1"]["last_production"], (today - timedelta(days=1)).isoformat()
        )
        self.assertEqual(find_recent_production([]), {})

    def test_inactive_plant_is_activated_only_when_untouched_and_newly_producing(self):
        today = date.today()
        db.session.add_all([
            Plant(plant_code=code, daily_tracker_name=code, erp_name=f"ERP {code}", is_active=False)
            for code in ("NEW", "ADM", "OLD", "RST")
        ])
        db.session.commit()
        db.session.add_all([
            # Explicit ids: SQLite does not auto-number BigInteger primary keys.
            PlantDailyVolume(id=1, plant_code="NEW", entry_date=today - timedelta(days=3), volume=10),
            PlantDailyVolume(id=2, plant_code="ADM", entry_date=today - timedelta(days=3), volume=10),
            PlantDailyVolume(id=3, plant_code="OLD", entry_date=today - timedelta(days=3), volume=10),
            PlantDailyVolume(id=4, plant_code="OLD", entry_date=today - timedelta(days=120), volume=10),
            PlantDailyVolume(id=5, plant_code="RST", entry_date=today - timedelta(days=3), volume=10),
            AuditLog(id=1, username="admin", action="plant_update",
                     details=json.dumps({"plant_code": "ADM", "active_changed": True, "is_active": False})),
            AuditLog(id=2, username="system", action="plant_master_reconcile",
                     details=json.dumps({"deactivated": ["RST"]})),
        ])
        db.session.commit()

        activated, reported = _activate_or_report_inactive_producing({"NEW", "ADM", "OLD", "RST"})
        db.session.commit()

        self.assertEqual([a["plant_code"] for a in activated], ["NEW"])
        self.assertEqual(sorted(r["plant_code"] for r in reported), ["ADM", "OLD", "RST"])
        self.assertTrue(db.session.get(Plant, "NEW").is_active)
        for code in ("ADM", "OLD", "RST"):
            self.assertFalse(db.session.get(Plant, code).is_active)
        self.assertEqual(_activate_or_report_inactive_producing(set()), ([], []))

    def test_future_master_sync_preserves_existing_status_and_tracker_name(self):
        db.session.add_all([
            Plant(
                plant_code="A1",
                daily_tracker_name="Approved Alpha",
                erp_name="Old ERP Alpha",
                region="North",
                is_active=True,
                is_manual_entry=False,
            ),
            Plant(
                plant_code="B1",
                daily_tracker_name="Inactive Beta",
                erp_name="ERP Beta",
                region="South",
                is_active=False,
                is_manual_entry=False,
            ),
        ])
        db.session.commit()

        organizations = [
            {"organization_code": "A1", "organization_name": "Current ERP Alpha"},
            {"organization_code": "B1", "organization_name": "Current ERP Beta"},
            {"organization_code": "N1", "organization_name": "Brand New Plant"},
        ]
        with patch(
            "app.services.erp_sync.fetch_erp_organizations",
            return_value=organizations,
        ):
            result = _sync_erp_organization_master()
            db.session.commit()

        self.assertEqual(result["new_plant_details"], [
            {"plant_code": "N1", "erp_name": "Brand New Plant"}
        ])
        self.assertTrue(db.session.get(Plant, "A1").is_active)
        self.assertEqual(db.session.get(Plant, "A1").daily_tracker_name, "Approved Alpha")
        self.assertEqual(db.session.get(Plant, "A1").erp_name, "Current ERP Alpha")
        self.assertFalse(db.session.get(Plant, "B1").is_active)
        self.assertEqual(db.session.get(Plant, "B1").daily_tracker_name, "Inactive Beta")
        self.assertTrue(db.session.get(Plant, "N1").is_active)
        self.assertEqual(db.session.get(Plant, "N1").daily_tracker_name, "Brand New Plant")
