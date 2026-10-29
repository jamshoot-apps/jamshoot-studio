"""Exercise the installed package from outside the source tree."""

import json
import subprocess
import sys
import sysconfig
import tempfile
import unittest
from pathlib import Path


class InstalledCliTests(unittest.TestCase):
    """The installed script and ``python -m jamshoot`` work from any folder."""

    def run_cli(self, *args: str, module: bool = False) -> subprocess.CompletedProcess[str]:
        """Run the installed entry point (or the module) from an unrelated folder."""
        if module:
            command = [sys.executable, "-m", "jamshoot"]
        else:
            name = "jamshoot.exe" if sys.platform == "win32" else "jamshoot"
            command = [str(Path(sysconfig.get_path("scripts")) / name)]
        with tempfile.TemporaryDirectory() as directory:
            return subprocess.run(
                [*command, *args], cwd=directory, capture_output=True, text=True, check=False
            )

    def test_catalog_resource_is_available_to_installed_entry_points(self):
        """Both entry points print the packaged catalog."""
        for module in (False, True):
            with self.subTest(module=module):
                result = self.run_cli("catalog", "--json", module=module)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stderr, "")
                catalog = json.loads(result.stdout)
                self.assertEqual(catalog["version"], 1)
                targets = catalog["targets"]
                self.assertEqual(len({target["id"] for target in targets}), len(targets))
                self.assertEqual(
                    {
                        (target["width"], target["height"])
                        for target in targets
                        if target["platform"] == "mac"
                    },
                    {(1280, 800), (1440, 900), (2560, 1600), (2880, 1800)},
                )
                self.assertEqual(len(targets), 62)

    def test_invalid_flags_fail_without_partial_json(self):
        """Unknown flags exit with status 2 and print nothing to stdout."""
        for flag in ("--unknown", "--js"):
            with self.subTest(flag=flag):
                result = self.run_cli("catalog", flag)
                self.assertEqual(result.returncode, 2)
                self.assertEqual(result.stdout, "")
                self.assertIn("unrecognized arguments", result.stderr)

    def test_unimplemented_commands_are_not_advertised(self):
        """Unknown subcommands such as ``migrate`` exit with status 2."""
        result = self.run_cli("migrate", "project.json")
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout, "")
        self.assertIn("invalid choice", result.stderr)
