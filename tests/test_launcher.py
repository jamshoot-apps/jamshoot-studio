"""The checkout launcher supports virtual environments created without pip."""

import os
import shutil
import subprocess
import tempfile
import unittest
import venv
from pathlib import Path


@unittest.skipIf(os.name == "nt", "The checkout launcher is a POSIX shell script.")
class LauncherTests(unittest.TestCase):
    """The ``studio`` launcher with a pip-free virtual environment."""

    def test_installed_studio_starts_without_pip(self):
        """With Bottle and ``jamshoot`` installed, the launcher skips pip and starts Studio."""
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shutil.copyfile(Path(__file__).resolve().parents[1] / "studio", root / "studio")
            venv.EnvBuilder(with_pip=False).create(root / ".venv")
            (root / "bottle.py").write_text('"""Installed Bottle stand-in."""\n')
            command = root / ".venv/bin/jamshoot"
            command.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
            command.chmod(0o755)
            result = subprocess.run(
                ["sh", str(root / "studio"), "--port", "9876"],
                capture_output=True,
                text=True,
                check=True,
            )
            self.assertEqual(
                result.stdout.splitlines(),
                ["studio", "--fallback-home", ".", "--open", "--port", "9876"],
            )


if __name__ == "__main__":
    unittest.main()
