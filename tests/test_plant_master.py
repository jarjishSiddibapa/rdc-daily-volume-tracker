from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

from flask import Flask
from openpyxl import Workbook

from app import db
from app.models import Plant
from app.services.erp_sync import _sync_erp_organization_master
from app.services.plant_master import (
    ActivePlantRecord,
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
