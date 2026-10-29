"""Project color styles: linking, overrides, detaching and validation."""

import copy
import json
import unittest

from jamshoot.core.planning import plan_project
from jamshoot.core.project import ProjectError, validate_project
from jamshoot.core.starter import init_project
from support import BRAND_COLORS, temporary_directory


class ColorStyleTests(unittest.TestCase):
    """Project palettes: references, overrides, detaching and strict validation."""

    def setUp(self):
        self.path = init_project(temporary_directory(self) / "project")
        self.data = json.loads(self.path.read_text())
        self.palette = dict(BRAND_COLORS)
        self.data["colorStyles"] = [{"id": "brand", "name": "Our brand", "colors": self.palette}]
        self.data["defaults"]["colorStyle"] = "brand"

    def jobs(self, data=None):
        """Planned jobs for ``data``, or for ``self.data``."""
        project = validate_project(self.data if data is None else data, self.path)
        return plan_project(project)["files"]

    def test_project_styles_resolve_without_builtin_theme_and_propagate_edits(self):
        """Linked slides follow palette edits and keep their own color overrides."""
        self.data["slides"].append(dict(copy.deepcopy(self.data["slides"][0]), id="second"))
        self.data["slides"][0]["style"] = {"colors": {"top": "#aabbcc"}}
        before = copy.deepcopy(self.data)
        first, second = self.jobs()
        self.assertEqual(first["colors"], self.palette | {"top": "#aabbcc"})
        self.assertEqual(second["colors"], self.palette)
        self.assertEqual(self.data, before)
        self.palette["bottom"] = "#102030"
        self.assertTrue(all(job["colors"]["bottom"] == "#102030" for job in self.jobs()))
        self.assertEqual(self.jobs()[0]["colors"]["top"], "#aabbcc")

    def test_palette_gradient_links_and_slides_override_it_per_field(self):
        """A palette's gradient follows its link; slide values win key by key."""
        self.data["colorStyles"][0]["gradient"] = {"kind": "radial", "centerY": 10}
        self.data["slides"].append(dict(copy.deepcopy(self.data["slides"][0]), id="second"))
        self.data["slides"][0]["style"] = {"gradient": {"radius": 150}}
        first, second = self.jobs()
        self.assertEqual(first["gradient"], {"kind": "radial", "centerY": 10, "radius": 150})
        self.assertEqual(second["gradient"], {"kind": "radial", "centerY": 10})
        self.data["slides"][1]["style"] = {"colorStyle": None, "gradient": {"kind": "solid"}}
        self.assertEqual(self.jobs()[1]["gradient"], {"kind": "solid"})
        self.data["colorStyles"][0]["gradient"] = {"angle": 400}
        with self.assertRaises(ProjectError):
            self.jobs()

    def test_new_reference_replaces_lower_color_overrides_and_null_can_detach(self):
        """A reference replaces inherited overrides; ``null`` detaches and keeps the colors."""
        self.data["defaults"]["colors"] = {"top": "#000000"}
        self.data["variants"] = [{"id": "one", "colors": {"bottom": "#000000"}}]
        self.data["slides"][0]["style"] = {"colorStyle": "brand", "colors": {"accent": "#ff0000"}}
        self.assertEqual(self.jobs()[0]["colors"], self.palette | {"accent": "#ff0000"})
        detached = dict(self.jobs()[0]["colors"])
        self.data["slides"][0]["style"] = {"colorStyle": None, "colors": detached}
        self.palette["bottom"] = "#ff0000"
        self.assertEqual(self.jobs()[0]["colors"], detached)

    def test_style_names_ids_palette_and_references_are_strict(self):
        """Blank names, partial palettes, unknown keys, duplicate ids and missing styles fail."""
        self.jobs()
        cases = []
        for invalid in (
            [{"id": "brand", "name": " ", "colors": self.palette}],
            [{"id": "brand", "name": "Name", "colors": {"top": "#123456"}}],
            [{"id": "brand", "name": "Name", "colors": self.palette, "typo": 1}],
            [self.data["colorStyles"][0], self.data["colorStyles"][0]],
        ):
            cases.append(self.data | {"colorStyles": invalid})
        for scope in ("defaults", "variants", "slides"):
            draft = copy.deepcopy(self.data)
            if scope == "defaults":
                draft["defaults"]["colorStyle"] = "missing"
            elif scope == "variants":
                draft["variants"] = [{"id": "one", "colorStyle": "missing"}]
            else:
                draft["slides"][0]["style"] = {"colorStyle": "missing"}
            cases.append(draft)
        for data in cases:
            with self.subTest(data=data), self.assertRaises(ProjectError):
                self.jobs(data)

    def test_free_colors_need_no_theme_or_saved_style(self):
        """A complete custom palette works without a theme or saved style."""
        self.data.pop("colorStyles")
        self.data["defaults"].pop("colorStyle")
        self.data["defaults"]["colors"] = self.palette
        self.assertEqual(self.jobs()[0]["colors"], self.palette)
