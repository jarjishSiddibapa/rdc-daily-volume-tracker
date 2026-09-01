from datetime import date
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch

from jinja2 import Environment

from app.services import report_generator


class ReportCacheTests(TestCase):
    def setUp(self):
        report_generator.invalidate_report_cache()

    def tearDown(self):
        report_generator.invalidate_report_cache()

    def test_reuses_and_invalidates_cached_report(self):
        calls = []

        def generate(day):
            calls.append(day)
            return {"day": day.isoformat(), "call": len(calls)}

        report_date = date(2026, 9, 1)
        with (
            patch.object(report_generator, "_REPORT_CACHE_TTL", 10),
            patch.object(report_generator, "_generate_report_uncached", side_effect=generate),
        ):
            first = report_generator.generate_report(report_date)
            second = report_generator.generate_report(report_date)
            self.assertIs(first, second)
            self.assertEqual(len(calls), 1)

            bypassed = report_generator.generate_report(report_date, use_cache=False)
            self.assertEqual(bypassed["call"], 2)

            report_generator.invalidate_report_cache()
            report_generator.generate_report(report_date)
            self.assertEqual(len(calls), 3)


class TemplateSyntaxTests(TestCase):
    def test_all_templates_parse(self):
        environment = Environment()
        template_dir = Path(__file__).parents[1] / "app" / "templates"
        for template in template_dir.glob("*.html"):
            with self.subTest(template=template.name):
                environment.parse(template.read_text(encoding="utf-8"))


class StartupAndLoadingContractTests(TestCase):
    def test_loading_message_is_present_on_app_and_auth_pages(self):
        root = Path(__file__).parents[1]
        message = "One sec… pretending this is very complicated 😎"
        self.assertIn(message, (root / "app" / "templates" / "base.html").read_text(encoding="utf-8"))
        self.assertIn(message, (root / "app" / "templates" / "_auth_loading.html").read_text(encoding="utf-8"))

    def test_windows_launcher_uses_project_directory_and_production_server(self):
        launcher = (Path(__file__).parents[1] / "start-all.bat").read_text(encoding="utf-8")
        self.assertIn('cd /d "%~dp0"', launcher)
        self.assertIn('copy /Y ".env.example" ".env"', launcher)
        self.assertIn("secrets.token_hex(32)", launcher)
        self.assertIn('"venv\\Scripts\\python.exe" server.py', launcher)
