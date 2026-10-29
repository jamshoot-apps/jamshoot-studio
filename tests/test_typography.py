"""Typography: per-field text settings, project and installed fonts, and their rendering."""

import copy
import json
import os
import shutil
import unittest
from unittest.mock import patch

from PIL import Image, ImageChops

from jamshoot.core.appearance import TYPOGRAPHY_DEFAULTS, resolve_text
from jamshoot.core.planning import plan_project
from jamshoot.core.project import ProjectError, validate_project
from jamshoot.core.starter import init_project
from jamshoot.render.compositor import render_job
from jamshoot.typefaces import Face, families, folder_faces, pick_face, style_weight
from studio_case import StudioCase
from support import installed_font, temporary_directory


def face(family: str, style: str, *, variable: bool = False) -> Face:
    """A test ``Face`` whose file is never read."""
    return Face(family, style, style_weight(style), "Italic" in style, variable, "x.ttf", 0)


class FaceTests(unittest.TestCase):
    """Style names give weights; a family resolves to its nearest upright face."""

    def test_style_names_map_to_css_weights(self):
        """``SemiBold`` maps to 600, not ``Bold``'s 700."""
        weights = {name: style_weight(name) for name in ("Thin", "SemiBold Italic", "Bold", "Book")}
        self.assertEqual(weights, {"Thin": 100, "SemiBold Italic": 600, "Bold": 700, "Book": 400})

    def test_nearest_upright_weight_or_the_variable_face(self):
        """Italics are skipped while an upright face exists; a variable face takes any weight."""
        faces = [face("Serif", "Regular"), face("Serif", "Bold"), face("Serif", "Black Italic")]
        self.assertEqual(pick_face(faces, "serif", 850), faces[1])
        self.assertEqual(pick_face(faces, "Serif", 450), faces[0])
        self.assertIsNone(pick_face(faces, "Sans", 400))
        variable = face("Sans", "Regular", variable=True)
        self.assertEqual(pick_face([face("Sans", "Bold"), variable], "Sans", 700), variable)

    def test_families_list_each_family_once_with_its_styles(self):
        """Faces group by family, sorted by name, and flag variable fonts."""
        faces = [face("b", "Bold"), face("A", "Regular", variable=True), face("b", "Thin")]
        listed = families(faces)
        self.assertEqual(
            listed,
            [
                {"family": "A", "styles": ["Regular"], "variable": True},
                {"family": "b", "styles": ["Bold", "Thin"], "variable": False},
            ],
        )


class TypographyTests(unittest.TestCase):
    """Typography per text field and scope, with fonts from ``assets/fonts``."""

    def setUp(self):
        self.path = init_project(temporary_directory(self) / "project")
        self.data = json.loads(self.path.read_text())
        # A black background and a magenta headline make the headline's ink measurable.
        self.data["defaults"].update(
            pattern="none", colors={"top": "#000000", "bottom": "#000000", "text": "#ff00ff"}
        )
        # Installed fonts must not decide these tests: one file draws the default and is
        # the project font.
        self.font = installed_font()
        environment = patch.dict(
            os.environ, {"JAMSHOOT_FONT_DIRS": "", "JAMSHOOT_FONT": str(self.font)}
        )
        environment.start()
        self.addCleanup(environment.stop)

    def jobs(self):
        """The planned jobs of ``self.data``."""
        return plan_project(validate_project(self.data, self.path))["files"]

    def add_project_font(self) -> str:
        """Copy the built-in font into the project's font folder; returns its family."""
        folder = self.path.parent / "assets/fonts"
        folder.mkdir(parents=True)
        shutil.copy(self.font, folder / f"Brand{self.font.suffix}")
        return families_in(folder)

    def test_scopes_merge_per_field_and_setting(self):
        """A slide overrides one headline setting and keeps the project's others."""
        self.data["defaults"]["typography"] = {"headline": {"size": 6, "uppercase": True}}
        self.data["slides"][0]["style"] = {"typography": {"headline": {"size": 7}}}
        self.assertEqual(self.jobs()[0]["typography"], {"headline": {"size": 7, "uppercase": True}})

    def test_text_follows_typography_then_the_layout(self):
        """Unset typography settings take the layout's built-in values."""
        self.data["defaults"]["typography"] = {
            "headline": {"size": 5, "lineHeight": 120},
            "subtitle": {"weight": 300, "letterSpacing": 4},
        }
        text = resolve_text(self.jobs()[0])
        self.assertEqual(
            text["headline"],
            {
                "font": None,
                "size": 5,
                "weight": TYPOGRAPHY_DEFAULTS["headline"]["weight"],
                "lineHeight": 120,
                "letterSpacing": 0,
                "uppercase": False,
            },
        )
        self.assertEqual((text["subtitle"]["weight"], text["subtitle"]["letterSpacing"]), (300, 4))

    def test_project_fonts_are_planned_and_missing_ones_name_the_fix(self):
        """A font in ``assets/fonts`` is planned; an unknown family fails."""
        family = self.add_project_font()
        self.data["defaults"]["typography"] = {"headline": {"font": family}}
        job = self.jobs()[0]
        self.assertEqual(list(job["fonts"]), ["headline"])
        self.assertTrue(
            job["fonts"]["headline"][0].endswith(f"assets/fonts/Brand{self.font.suffix}")
        )
        self.data["defaults"]["typography"] = {"headline": {"font": "Nowhere Sans"}}
        with self.assertRaisesRegex(ProjectError, "Nowhere Sans.*Project → Typography"):
            self.jobs()

    def test_case_spacing_and_fonts_change_only_their_field(self):
        """Uppercase and spacing change the headline; the same font from the project matches."""
        plain = render_job(self.jobs()[0])
        self.data["defaults"]["typography"] = {"headline": {"uppercase": True}}
        upper = render_job(self.jobs()[0])
        self.data["defaults"]["typography"] = {"headline": {"letterSpacing": 20}}
        spaced = render_job(self.jobs()[0])
        for image in (upper, spaced):
            self.assertIsNotNone(ImageChops.difference(plain, image).getbbox())
        self.assertGreater(ink_width(spaced), ink_width(plain))
        self.data["defaults"]["typography"] = {"headline": {"font": self.add_project_font()}}
        self.assertEqual(render_job(self.jobs()[0]).tobytes(), plain.tobytes())

    def test_schema_bounds_typography(self):
        """Out-of-range settings, unknown fields and blank font names fail."""
        invalid: list[dict[str, dict[str, object]]] = [
            {"headline": {"size": 30}},
            {"caption": {}},
            {"headline": {"font": " "}},
        ]
        for typography in invalid:
            data = copy.deepcopy(self.data)
            data["defaults"]["typography"] = typography
            with self.assertRaises(ProjectError):
                validate_project(data, self.path)


def families_in(folder) -> str:
    """The family of the one font in ``folder``."""
    return folder_faces(folder)[0].family


def ink_width(image: Image.Image) -> int:
    """Width of the magenta ink in ``image``, in pixels."""
    red, green, _ = image.split()
    mask = ImageChops.subtract(red, green).point([0] * 129 + [255] * 127)
    box = mask.getbbox()
    return 0 if box is None else box[2] - box[0]


class FontApiTests(StudioCase):
    """Fonts upload into the project and list beside installed ones."""

    def test_upload_lists_the_family_and_rejects_other_files(self):
        """A valid font is stored and listed; bad names or files get 400."""
        font = installed_font()
        with patch.dict(os.environ, {"JAMSHOOT_FONT_DIRS": ""}):
            content = font.read_bytes()
            status, payload = self.client.json(
                f"{self.api}/fonts?name=Brand%20Sans{font.suffix}",
                "POST",
                content,
                content_type="font/ttf",
            )
            self.assertEqual(status, 201)
            self.assertEqual(payload["path"], f"assets/fonts/Brand-Sans{font.suffix}")
            self.assertTrue((self.path.parent / payload["path"]).is_file())
            self.assertEqual(len(payload["families"]), 1)
            status, listed = self.client.json(f"{self.api}/fonts")
            self.assertEqual(status, 200)
            self.assertEqual([item["family"] for item in listed["project"]], payload["families"])
            self.assertEqual(listed["system"], [])
            for name, body in (("evil.exe", content), ("fake.ttf", b"not a font")):
                status, _ = self.client.json(
                    f"{self.api}/fonts?name={name}", "POST", body, content_type="font/ttf"
                )
                self.assertEqual(status, 400, name)


if __name__ == "__main__":
    unittest.main()
