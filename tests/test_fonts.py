"""Default fonts: JAMSHOOT_FONT, else an installed sans-serif family; never a download."""

import ast
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jamshoot.core.planning import plan_project
from jamshoot.core.project import ProjectError, load_project
from jamshoot.core.starter import init_project
from jamshoot.fonts import default_face, default_families
from jamshoot.render.compositor import render_job
from jamshoot.typefaces import system_faces
from support import ROOT

# Modules that fetch from the network; the package imports none of them.
NETWORK_MODULES = ("urllib.request", "http.client", "requests", "ftplib")


def without_font_setting() -> dict[str, str]:
    """The environment without ``JAMSHOOT_FONT``."""
    return {key: value for key, value in os.environ.items() if key != "JAMSHOOT_FONT"}


class FontTests(unittest.TestCase):
    """Text uses the ``JAMSHOOT_FONT`` file or an installed family, never a download."""

    def test_explicit_font_is_used_and_a_missing_one_is_actionable(self):
        """``JAMSHOOT_FONT`` wins; a missing file raises an error about that setting."""
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "custom.ttf"
            with patch.dict(os.environ, {"JAMSHOOT_FONT": str(path)}):
                with self.assertRaisesRegex(ProjectError, "JAMSHOOT_FONT"):
                    default_face()
                path.write_bytes(b"external font")
                self.assertEqual(default_face(700), (str(path), 0))

    def test_an_installed_default_family_draws_text_by_weight(self):
        """Without a setting, regular and bold come from an installed default family."""
        with patch.dict(os.environ, without_font_setting(), clear=True):
            regular, bold = default_face(400), default_face(700)
        families = {
            (face.path, face.number): face
            for face in system_faces()
            if face.family in default_families()
        }
        self.assertIn(regular, families)
        if not families[bold].variable:
            self.assertNotEqual(regular, bold)
            self.assertGreater(families[bold].weight, families[regular].weight)

    def test_no_installed_default_names_the_fixes_and_raw_still_renders(self):
        """With no default font, ``raw`` still renders; text layouts fail with the fixes."""
        with tempfile.TemporaryDirectory() as directory:
            project = load_project(init_project(Path(directory) / "project"))
            job = plan_project(project)["files"][0]
            environment = without_font_setting() | {"JAMSHOOT_FONT_DIRS": ""}
            with patch.dict(os.environ, environment, clear=True):
                job["layout"] = "raw"
                with render_job(job) as image:
                    self.assertEqual(image.size, (1280, 800))
                job["layout"] = "window-top"
                with self.assertRaisesRegex(ProjectError, "JAMSHOOT_FONT.*Typography"):
                    render_job(job)

    def test_the_package_never_downloads(self):
        """No package module imports a network client."""
        for source in (ROOT / "src" / "jamshoot").rglob("*.py"):
            for node in ast.walk(ast.parse(source.read_text("utf-8"))):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom):
                    names = [node.module or ""]
                for name in names:
                    self.assertFalse(name.startswith(NETWORK_MODULES), f"{source.name}: {name}")


if __name__ == "__main__":
    unittest.main()
