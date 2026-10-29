"""CLI project commands, run from a temporary folder."""

import json
import unittest

from support import run_jamshoot, temporary_directory


class ProjectCliTests(unittest.TestCase):
    """init, validate and plan from a folder with spaces and non-ASCII names."""

    def setUp(self):
        self.root = temporary_directory(self, prefix="jamshoot project ")
        self.project = self.root / "Пример проекта"

    def cli(self, *args):
        """Run the CLI from the temporary folder."""
        return run_jamshoot(*args, cwd=self.root)

    def test_init_validate_plan_happy_path_without_manual_edits(self):
        """``init`` writes a starter that validates and plans one file unedited."""
        created = self.cli("init", self.project, "--json")
        self.assertEqual(created.returncode, 0, created.stderr)
        self.assertEqual(created.stderr, "")
        path = self.project / "project.json"
        self.assertEqual(json.loads(created.stdout)["project"], str(path.resolve()))
        self.assertTrue((self.project / "project.schema.json").is_file())
        checked = self.cli("validate", path, "--json")
        self.assertEqual(checked.returncode, 0, checked.stderr)
        self.assertTrue(json.loads(checked.stdout)["valid"])
        planned = self.cli("plan", path, "--json")
        self.assertEqual(planned.returncode, 0, planned.stderr)
        plan = json.loads(planned.stdout)
        self.assertEqual(plan["fileCount"], 1)
        self.assertEqual(
            plan["files"][0]["output"], "default/en-US/appstore.mac.1280x800/01-overview.png"
        )
        self.assertEqual(
            (self.project / "assets/screenshot.png").read_bytes()[:8], b"\x89PNG\r\n\x1a\n"
        )
        self.assertFalse((self.project / "output").exists())

    def test_init_refuses_to_overwrite_existing_directory(self):
        """``init`` fails on an existing folder and leaves it untouched."""
        self.project.mkdir()
        original = self.project / "notes.txt"
        original.write_text("keep me")
        result = self.cli("init", self.project, "--json")
        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertEqual(original.read_text(), "keep me")
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "invalid_project")
        self.assertFalse((self.project / "project.json").exists())

    def test_invalid_config_is_machine_readable_without_traceback(self):
        """An invalid project prints a JSON error to stdout, with no traceback."""
        path = self.root / "bad.json"
        path.write_text('{"version":99}')
        result = self.cli("validate", path, "--json")
        self.assertEqual(result.returncode, 1)
        self.assertEqual(result.stderr, "")
        self.assertEqual(json.loads(result.stdout)["error"]["code"], "invalid_project")
        self.assertNotIn("Traceback", result.stdout)

    def test_missing_file_and_malformed_json_are_user_errors(self):
        """A missing or malformed project file exits 1 with a message on stderr."""
        path = self.root / "missing.json"
        for text in (None, "{"):
            if text is not None:
                path.write_text(text)
            result = self.cli("validate", path)
            self.assertEqual(result.returncode, 1)
            self.assertEqual(result.stdout, "")
            self.assertNotIn("Traceback", result.stderr)
            self.assertIn("project", result.stderr.lower())
