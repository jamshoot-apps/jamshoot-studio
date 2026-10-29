"""Public distributions reject private files; project ZIPs reject external symlinks."""

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from check_distribution import _check_archive

from jamshoot.core.project import ProjectError
from jamshoot.library import ProjectLibrary

ROOT = Path(__file__).resolve().parents[1]


class PublicReleaseTests(unittest.TestCase):
    """Exercise the boundaries that prevent local data from entering public archives."""

    def test_project_zip_rejects_external_symlink_files_and_directories(self):
        """Archive export fails on an external symlink in ``assets`` or as the schema."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            library = ProjectLibrary(root / "home")
            created = library.create("Demo", "iphone")
            folder = Path(created["path"]).parent
            external = root / "external"
            external.mkdir()
            (external / "private.txt").write_text("private marker")
            for relative, target in (
                ("assets/private.txt", external / "private.txt"),
                ("assets/external", external),
                ("project.schema.json", external / "private.txt"),
            ):
                with self.subTest(relative=relative):
                    link = folder / relative
                    if link.exists():
                        link.unlink()
                    try:
                        link.symlink_to(target, target_is_directory=target.is_dir())
                    except OSError as error:
                        self.skipTest(f"Symlinks unavailable: {error}")
                    with self.assertRaisesRegex(ProjectError, "inside the project"):
                        library.export_archive(created["id"])
                    link.unlink()

    def test_archives_reject_private_projects_credentials_and_local_state(self):
        """The archive check exits on private projects, credentials, keys and local state."""
        with patch("check_distribution.package_files", return_value=[]):
            for member in (
                "projects/customer/project.json",
                "projects/demo/assets/private.png",
                "src/jamshoot/.env",
                "docs/.aws/credentials",
                "src/jamshoot/private.pem",
                "docs/.DS_Store",
            ):
                with self.subTest(member=member), self.assertRaises(SystemExit):
                    _check_archive("sdist", {member}, "src/")

    def test_git_ignores_private_projects_and_credentials_but_keeps_demo(self):
        """Git ignores private projects, credentials and local state, not the demo files."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copyfile(ROOT / ".gitignore", root / ".gitignore")
            subprocess.run(["git", "init", "--quiet", str(root)], check=True)
            paths = [
                "projects/customer/project.json",
                "projects/demo/exports/export.png",
                ".env",
                "src/jamshoot/.env.local",
                ".aws/credentials",
                "private.pem",
                "trash/project.json",
                "incoming/capture.png",
                "projects/demo/assets/private.png",
                "projects/demo/notes.txt",
                "projects/demo/project.json",
                "projects/demo/assets/screenshot.png",
            ]
            result = subprocess.run(
                ["git", "check-ignore", "--no-index", "--stdin"],
                cwd=root,
                input="\n".join(paths) + "\n",
                text=True,
                capture_output=True,
                check=False,
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.splitlines(), paths[:-2])
