"""The release preflight script, run against temporary checkouts."""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


class ReleasePreflightTests(unittest.TestCase):
    """The release preflight checks versions and extracts the changelog section."""

    def test_preflight_accepts_matching_release_and_writes_only_its_notes(self):
        """A matching version exits 0 and writes only its changelog section."""
        self.run_preflight(
            "0.1.0", "0.1.0", "## [0.1.0] - 2026-10-15\n\n### Added\n\n- First.\n", 0
        )

    def test_preflight_rejects_mismatch_development_version_and_missing_changelog(self):
        """Bad, mismatched or development versions and unreleased notes exit 1 with no notes."""
        for version, package, notes in (
            ("0.1.0", "0.2.0", "## [0.1.0] - 2026-10-15\n\n- First."),
            ("0.1.0.dev0", "0.1.0.dev0", "## Unreleased\n\n- First."),
            ("0.1.0", "0.1.0", "## Unreleased\n\n- First."),
            ("0.1.0; echo unsafe", "0.1.0", "## Unreleased"),
        ):
            with self.subTest(version=version, package=package):
                self.run_preflight(version, package, notes, 1)

    def run_preflight(self, version, package, notes, expected):
        """Run the preflight on a fake checkout and check its exit code and notes."""
        script = Path(__file__).resolve().parents[1] / ".github/scripts/prepare_release.py"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            package_dir = root / "src/jamshoot"
            package_dir.mkdir(parents=True)
            (package_dir / "__init__.py").write_text(f'__version__ = "{package}"\n')
            (root / "CHANGELOG.md").write_text("# Changelog\n\n" + notes)
            output = root / "notes.md"
            result = subprocess.run(
                [
                    sys.executable,
                    str(script),
                    "--root",
                    str(root),
                    "--version",
                    version,
                    "--output",
                    str(output),
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(result.returncode, expected, result.stderr)
            if expected == 0:
                self.assertIn("- First.", output.read_text())
                self.assertNotIn("# Changelog", output.read_text())
            else:
                self.assertFalse(output.exists())
