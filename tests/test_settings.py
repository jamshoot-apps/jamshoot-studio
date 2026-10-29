"""Settings: packaged defaults, the user's settings file and the chosen Studio folder."""

import json
import os
import unittest
from pathlib import Path
from unittest.mock import patch

from jamshoot.core.project import ProjectError
from jamshoot.core.starter import init_project
from jamshoot.library import ProjectLibrary
from jamshoot.server import Session, create_app
from jamshoot.settings import (
    default_settings,
    save_settings,
    saved_settings,
    settings_path,
    studio_home,
)
from support import ORIGIN, WsgiClient, temporary_directory


class SettingsFileTests(unittest.TestCase):
    """Defaults ship in the package; the user's file overrides them."""

    def setUp(self):
        self.root = temporary_directory(self)
        self.file = self.root / "config/settings.json"
        environment = patch.dict(os.environ, {"JAMSHOOT_SETTINGS": str(self.file)})
        environment.start()
        self.addCleanup(environment.stop)

    def test_the_default_studio_folder_comes_from_the_packaged_settings(self):
        """With no saved choice, the packaged default ``~/JamShoot`` is the Studio folder."""
        self.assertEqual(default_settings(), {"home": "~/JamShoot"})
        self.assertEqual(saved_settings(), {})
        self.assertEqual(studio_home(), (Path.home() / "JamShoot", "default"))

    def test_command_line_environment_and_saved_choice_take_precedence_in_order(self):
        """``--home`` > ``JAMSHOOT_HOME`` > saved setting > fallback, in that order."""
        fallback = self.root / "checkout"
        self.assertEqual(studio_home(None, fallback), (fallback, "fallback"))
        save_settings({"home": str(self.root / "saved")})
        self.assertEqual(studio_home(None, fallback), (self.root / "saved", "settings"))
        with patch.dict(os.environ, {"JAMSHOOT_HOME": str(self.root / "env")}):
            self.assertEqual(studio_home(None, fallback), (self.root / "env", "JAMSHOOT_HOME"))
            self.assertEqual(studio_home(self.root / "flag"), (self.root / "flag", "--home"))

    def test_saving_merges_into_the_file_and_creates_its_folder(self):
        """Other saved keys survive; the file is readable JSON with a trailing newline."""
        save_settings({"theme": "dark"})
        save_settings({"home": "/tmp/studio"})
        text = self.file.read_text("utf-8")
        self.assertEqual(json.loads(text), {"theme": "dark", "home": "/tmp/studio"})
        self.assertTrue(text.endswith("\n"))
        self.assertEqual([path.name for path in self.file.parent.iterdir()], ["settings.json"])

    def test_a_failed_save_removes_its_temporary_file_and_reports_the_error(self):
        """A failed write or replace leaves no ``.settings-*`` file behind and re-raises."""
        failures = (
            ("write", patch.object(json, "dump", side_effect=OSError("disk full"))),
            ("replace", patch.object(Path, "replace", side_effect=OSError("disk full"))),
        )
        for label, failure in failures:
            with (
                self.subTest(label),
                failure,
                self.assertRaisesRegex(OSError, "disk full"),
            ):
                save_settings({"theme": "dark"})
            self.assertEqual(list(self.file.parent.glob(".settings-*")), [])
        self.assertFalse(self.file.exists())

    def test_a_broken_settings_file_is_reported_with_its_path(self):
        """Invalid JSON or a non-object settings file raises ProjectError with its path."""
        self.file.parent.mkdir(parents=True)
        for content in ("{", "[]"):
            with self.subTest(content=content):
                self.file.write_text(content, encoding="utf-8")
                with self.assertRaisesRegex(ProjectError, str(self.file)):
                    saved_settings()

    def test_the_settings_file_lives_in_each_systems_settings_folder(self):
        """macOS Application Support, Windows APPDATA, XDG config elsewhere."""
        home = Path.home()
        cases = {
            "darwin": ({}, home / "Library/Application Support/JamShoot Studio/settings.json"),
            "win32": ({"APPDATA": "/appdata"}, Path("/appdata/JamShoot Studio/settings.json")),
            "linux": ({"XDG_CONFIG_HOME": "/xdg"}, Path("/xdg/jamshoot-studio/settings.json")),
        }
        for platform, (environment, expected) in cases.items():
            with (
                self.subTest(platform=platform),
                patch("jamshoot.settings.sys.platform", platform),
                patch.dict(os.environ, environment),
            ):
                os.environ.pop("JAMSHOOT_SETTINGS")
                self.assertEqual(settings_path(), expected)


class StudioFolderTests(unittest.TestCase):
    """The ``/api/settings`` routes read and change the Studio folder."""

    def setUp(self):
        self.root = temporary_directory(self)
        self.file = self.root / "settings.json"
        environment = patch.dict(os.environ, {"JAMSHOOT_SETTINGS": str(self.file)})
        environment.start()
        self.addCleanup(environment.stop)
        self.library = ProjectLibrary(self.root / "first", "fallback")
        self.client = WsgiClient(
            create_app(self.library, Session("settings-token", ORIGIN)), "settings-token"
        )

    def test_settings_report_the_folder_what_chose_it_and_the_file(self):
        """GET reports the resolved folder, its source and the settings file path."""
        status, settings = self.client.json("/api/settings")
        self.assertEqual(status, 200)
        self.assertEqual(
            settings,
            {"home": str(self.root / "first"), "source": "fallback", "file": str(self.file)},
        )

    def test_saving_a_folder_switches_the_library_now_and_keeps_it(self):
        """PUT switches the library at once, creates a missing folder and saves the choice."""
        self.library.create("Old", "iphone")
        opened = self.library.open_in_place(init_project(self.root / "elsewhere"))
        target = self.root / "second"
        status, settings = self.client.json("/api/settings", "PUT", {"home": f" {target} "})
        self.assertEqual(status, 200)
        self.assertEqual((settings["home"], settings["source"]), (str(target), "settings"))
        self.assertTrue((target / "projects").is_dir())
        self.assertEqual(json.loads(self.file.read_text("utf-8")), {"home": str(target)})
        listed = self.client.json("/api/projects")[1]
        self.assertEqual(listed["home"], str(target / "projects"))
        self.assertEqual([item["id"] for item in listed["projects"]], [opened["id"]])

    def test_a_choice_that_cannot_be_saved_leaves_the_old_folder_in_place(self):
        """A failed save returns 400, and the library and GET keep the previous folder."""
        old = self.library.create("Old", "iphone")
        opened = self.library.open_in_place(init_project(self.root / "elsewhere"))
        target = self.root / "second"
        self.file.write_text("{", encoding="utf-8")
        status, body = self.client.json("/api/settings", "PUT", {"home": str(target)})
        self.assertEqual(status, 400)
        self.assertIn(str(self.file), body["error"]["message"])
        with patch("jamshoot.server.projects.save_settings", side_effect=OSError("read-only")):
            status, body = self.client.json("/api/settings", "PUT", {"home": str(target)})
        self.assertEqual((status, body["error"]["message"]), (400, "read-only"))
        self.assertEqual(self.file.read_text("utf-8"), "{")
        self.assertEqual(self.library.home, self.root / "first")
        settings = self.client.json("/api/settings")[1]
        self.assertEqual(settings["home"], str(self.root / "first"))
        self.assertEqual(settings["source"], "fallback")
        listed = self.client.json("/api/projects")[1]
        self.assertEqual(listed["home"], str(self.root / "first" / "projects"))
        listed_ids = [item["id"] for item in listed["projects"]]
        self.assertIn(opened["id"], listed_ids)
        self.assertIn(old["id"], listed_ids)

    def test_a_home_starting_with_a_tilde_is_saved_and_reported_expanded(self):
        """A ``~/`` folder expands to the user's home before it is saved and reported."""
        home = self.root / "home"
        with patch.dict(os.environ, {"HOME": str(home), "USERPROFILE": str(home)}):
            status, settings = self.client.json("/api/settings", "PUT", {"home": "~/Studio"})
        self.assertEqual(status, 200)
        self.assertEqual(settings["home"], str(home / "Studio"))
        self.assertEqual(json.loads(self.file.read_text("utf-8")), {"home": str(home / "Studio")})
        self.assertTrue((home / "Studio" / "projects").is_dir())

    def test_saving_rejects_empty_relative_and_unusable_folders(self):
        """Only a full path to a folder that can be created is accepted; nothing is saved."""
        (self.root / "a-file").write_text("", encoding="utf-8")
        for home, message in (
            ("", "Enter the Studio folder"),
            (42, "Enter the Studio folder"),
            ("projects", "full path"),
            (str(self.root / "a-file"), "Cannot create Studio home"),
        ):
            with self.subTest(home=home):
                status, body = self.client.json("/api/settings", "PUT", {"home": home})
                self.assertEqual(status, 400)
                self.assertIn(message, body["error"]["message"])
        self.assertFalse(self.file.exists())
        self.assertEqual(self.library.home, self.root / "first")


if __name__ == "__main__":
    unittest.main()
