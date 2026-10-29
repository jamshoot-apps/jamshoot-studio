"""Layout templates, per-slide overrides, and text and screenshot spacing."""

import copy
import json
import unittest
from typing import Any

from PIL import Image

from jamshoot.core.appearance import LAYOUT_DEFAULTS, layout_defaults, typography_defaults
from jamshoot.core.planning import plan_project
from jamshoot.core.project import ProjectError, validate_project
from jamshoot.core.starter import init_project
from jamshoot.render.compositor import BADGE_DOT, BADGE_PAD_X, render_job
from support import temporary_directory

FRAME = (255, 0, 255)
SCREENSHOT = (230, 59, 99)
WIDE = "custom.3840x1646"


class LayoutTests(unittest.TestCase):
    """Saved layout templates, per-field overrides and the rendered spacing."""

    def setUp(self):
        self.path = init_project(temporary_directory(self) / "project")
        self.data = json.loads(self.path.read_text())
        Image.new("RGB", (640, 400), "#2060a0").save(self.path.parent / "assets/screenshot.png")
        # A flat black background and a magenta window frame make geometry measurable.
        self.data["defaults"].update(
            pattern="none",
            colors={"top": "#000000", "bottom": "#000000", "frame": "#ff00ff"},
        )

    def jobs(self):
        """The planned jobs of ``self.data``."""
        return plan_project(validate_project(self.data, self.path))["files"]

    def window_top(self, **settings):
        """The first row of the app window at the canvas's horizontal center."""
        self.data["defaults"]["layoutSettings"] = settings
        image = render_job(self.jobs()[0])
        x = image.width // 2
        return next(y for y in range(image.height) if image.getpixel((x, y)) == FRAME)

    def test_templates_link_and_local_settings_override_per_field(self):
        """A template link replaces inherited settings; slide settings override single fields."""
        self.data["layoutStyles"] = [
            {"id": "airy", "name": "Airy", "layoutSettings": {"topMargin": 12, "labelGap": 3}},
            {"id": "tight", "name": "Tight", "layoutSettings": {"topMargin": 2}},
        ]
        self.data["defaults"].update(layoutStyle="airy", layoutSettings={"screenshotGap": 8})
        self.data["slides"].append(dict(copy.deepcopy(self.data["slides"][0]), id="second"))
        self.data["slides"][0]["style"] = {"layoutSettings": {"labelGap": 2}}
        self.data["slides"][1]["style"] = {"layoutStyle": "tight"}
        first, second = self.jobs()
        self.assertEqual(
            first["layoutSettings"], {"topMargin": 12, "labelGap": 2, "screenshotGap": 8}
        )
        self.assertEqual(second["layoutSettings"], {"topMargin": 2})
        self.data["slides"][1]["style"] = {"layoutStyle": None}
        self.assertEqual(self.jobs()[1]["layoutSettings"], {})

    def test_layout_settings_and_template_references_are_strict(self):
        """Unknown templates, layouts or settings, bad values and duplicate ids fail."""
        invalid = [
            {"layoutStyle": "missing"},
            {"layout": "banner"},
            {"layoutSettings": {"padding": 4}},
            {"layoutSettings": {"screenshotGap": -1}},
            {"layoutSettings": {"lineHeight": 120}},
        ]
        for style in invalid:
            with self.subTest(style=style):
                data = copy.deepcopy(self.data)
                data["slides"][0]["style"] = style
                with self.assertRaises(ProjectError):
                    validate_project(data, self.path)
        self.data["layoutStyles"] = [
            {"id": "same", "name": "A", "layoutSettings": {}},
            {"id": "same", "name": "B", "layoutSettings": {}},
        ]
        with self.assertRaisesRegex(ProjectError, "duplicate"):
            validate_project(self.data, self.path)

    def test_built_in_values_follow_orientation_and_large_device(self):
        """Landscape and ``device-focus`` adjust the portrait defaults and keep every key."""
        portrait = layout_defaults("device-top", (1179, 2556))
        landscape = layout_defaults("window-top", (1280, 800))
        focus = layout_defaults("device-focus", (1179, 2556))
        self.assertEqual(portrait, LAYOUT_DEFAULTS)
        self.assertEqual(set(landscape), set(portrait))
        self.assertGreater(focus["screenshotWidth"], portrait["screenshotWidth"])
        headline = {
            name: typography_defaults(layout, size)["headline"]["size"]
            for name, layout, size in [
                ("portrait", "device-top", (1179, 2556)),
                ("landscape", "window-top", (1280, 800)),
                ("focus", "device-focus", (1179, 2556)),
            ]
        }
        self.assertGreater(headline["landscape"], headline["portrait"])
        self.assertLess(headline["focus"], headline["portrait"])

    def test_screenshot_gap_moves_only_the_screenshot(self):
        """Each point of ``screenshotGap`` or ``topMargin`` moves the window 1% of the height."""
        job = self.jobs()[0]
        height = job["height"]
        near, far = self.window_top(screenshotGap=2), self.window_top(screenshotGap=8)
        self.assertAlmostEqual(far - near, height * 0.06, delta=2)
        lower = self.window_top(screenshotGap=2, topMargin=10)
        top = layout_defaults(job["layout"], (job["width"], height))["topMargin"]
        self.assertAlmostEqual(lower - near, height * (10 - top) / 100, delta=2)

    def test_screenshot_top_pins_the_screenshot_whatever_the_text(self):
        """A ``screenshotTop`` below the text pins the window; text past it pushes it down."""
        localized = self.data["slides"][0]["copy"]["en-US"]
        localized["headline"] = "Plan"
        auto_short = self.window_top()
        short = self.window_top(screenshotTop=40)
        localized["headline"] = "Plan the launch with your whole team, every single day"
        self.assertGreater(self.window_top(), auto_short)
        self.assertEqual(self.window_top(screenshotTop=40), short)
        self.assertEqual(self.window_top(screenshotTop=5), self.window_top())

    def test_typography_changes_the_text(self):
        """Weight, size and line height each change the rendered headline."""
        localized = self.data["slides"][0]["copy"]["en-US"]
        localized["headline"] = "Plan the launch with your whole team, every single day of the week"
        variants = [
            {},
            {"weight": 300},
            {"size": 7},
            {"lineHeight": 150},
        ]
        rendered = set()
        for settings in variants:
            self.data["defaults"]["typography"] = {"headline": settings}
            image = render_job(self.jobs()[0])
            rendered.add(image.crop((0, 0, image.width, image.height // 3)).tobytes())
        self.assertEqual(len(rendered), len(variants))

    def test_spacing_that_leaves_no_room_for_the_screenshot_fails(self):
        """Spacing that leaves too little room for the screenshot fails."""
        self.data["defaults"]["layoutSettings"] = {
            "topMargin": 30,
            "screenshotGap": 30,
            "bottomMargin": 20,
        }
        with self.assertRaisesRegex(ProjectError, "too little room"):
            render_job(self.jobs()[0])

    def test_guides_report_where_text_and_screenshot_landed(self):
        """Guides report text, column and window geometry without changing pixels."""
        self.data["defaults"]["layoutSettings"] = {"topMargin": 10}
        job = self.jobs()[0]
        guides: dict = {}
        image = render_job(job, guides)
        self.assertEqual(image.tobytes(), render_job(job).tobytes())
        self.assertEqual(guides["canvas"], [image.width, image.height])
        headline = guides["copy"]["headline"]
        self.assertGreaterEqual(headline[1], image.height * 0.1 - 1)
        self.assertLess(headline[3], guides["frame"][1])
        self.assertEqual(guides["frame"][1], self.window_top(topMargin=10))
        left, right = guides["text"]
        width = layout_defaults("window-top", image.size)["textWidth"]
        self.assertAlmostEqual(right - left, image.width * width / 100)
        self.assertGreater(guides["sizes"]["headline"], 0)


class BadgeTests(unittest.TestCase):
    """``labelStyle: "badge"`` draws the feature label in an accent pill with a dot."""

    def setUp(self):
        self.path = init_project(temporary_directory(self) / "project")
        self.data = json.loads(self.path.read_text())
        Image.new("RGB", (640, 400), "#2060a0").save(self.path.parent / "assets/screenshot.png")
        self.data["defaults"].update(
            pattern="none",
            colors={"top": "#000000", "bottom": "#000000", "accent": "#ff0000"},
        )
        self.data["slides"][0]["copy"]["en-US"].update(featureLabel="New season")

    def render(self, label_style: str | None = None) -> tuple[Image.Image, dict[str, Any]]:
        """Render the first job with guides, setting ``labelStyle`` first if given."""
        if label_style:
            self.data["defaults"]["labelStyle"] = label_style
        guides: dict[str, Any] = {}
        return render_job(self.jobs()[0], guides), guides

    def jobs(self) -> list[dict[str, Any]]:
        """The planned jobs of ``self.data``."""
        return plan_project(validate_project(self.data, self.path))["files"]

    def test_text_is_the_default(self):
        """``labelStyle`` defaults to ``text``."""
        self.assertEqual(self.jobs()[0]["labelStyle"], "text")

    def test_large_badge_shrinks_with_its_padding_to_fit_the_column(self):
        """A badge too wide for its column shrinks to fit, by at most 40 percent."""
        self.data["targets"] = ["custom.1200x2600"]
        self.data["defaults"]["layout"] = "auto"
        self.data["defaults"]["typography"] = {"featureLabel": {"size": 12}}
        self.data["slides"][0]["copy"]["en-US"].update(
            featureLabel="H", headline="Plan", subtitle=""
        )
        _, guides = self.render("badge")
        left, _, right, _ = guides["copy"]["featureLabel"]
        column_left, column_right = guides["text"]
        self.assertGreaterEqual(left, column_left)
        self.assertLessEqual(right, column_right)
        self.assertGreaterEqual(guides["sizes"]["featureLabel"], round(2600 * 0.12 * 0.6))
        self.assertLess(guides["sizes"]["featureLabel"], round(2600 * 0.12))

    def test_badge_wraps_the_label_and_moves_the_text_down(self):
        """A badge starts at the plain label's top, is larger, and pushes the headline down."""
        plain = self.render()[1]["copy"]
        badge = self.render("badge")[1]["copy"]
        left, top, right, bottom = badge["featureLabel"]
        plain_left, plain_top, plain_right, plain_bottom = plain["featureLabel"]
        self.assertAlmostEqual(top, plain_top, delta=1)
        self.assertGreater(bottom - top, plain_bottom - plain_top)
        self.assertGreater(right - left, plain_right - plain_left)
        self.assertGreater(badge["headline"][1], plain["headline"][1])

    def test_badge_is_a_tinted_pill_with_a_solid_accent_dot(self):
        """The pill is the accent at low opacity; the dot is the solid accent."""
        image, guides = self.render("badge")
        left, top, _, bottom = guides["copy"]["featureLabel"]
        size, middle = guides["sizes"]["featureLabel"], round((top + bottom) / 2)
        tint = image.getpixel((round(left + size * 0.4), middle))
        dot = image.getpixel((round(left + size * (BADGE_PAD_X + BADGE_DOT / 2)), middle))
        assert isinstance(tint, tuple) and isinstance(dot, tuple)
        self.assertTrue(10 < tint[0] < 60 and tint[1] == tint[2] == 0)
        self.assertGreater(dot[0], 240)

    def test_badge_centers_the_label_in_the_pill(self):
        """The capitals are centered in the pill, vertically and horizontally."""
        self.data["slides"][0]["copy"]["en-US"].update(featureLabel="HANDS")
        image, guides = self.render("badge")
        left, top, right, bottom = guides["copy"]["featureLabel"]
        size = guides["sizes"]["featureLabel"]
        inside = image.crop((round(left), round(top), round(right), round(bottom))).convert("RGB")
        # Bright text and dot against the dark tinted pill.
        mask = Image.eval(inside.getchannel("R"), lambda v: 255 if v > 200 else 0)
        ink_left, ink_top, ink_right, ink_bottom = mask.getbbox() or (0, 0, 0, 0)
        self.assertAlmostEqual(ink_top, inside.height - ink_bottom, delta=2)
        self.assertAlmostEqual(ink_left, inside.width - ink_right, delta=size * 0.1)

    def test_unknown_label_style_is_rejected(self):
        """An unknown ``labelStyle`` fails validation."""
        self.data["defaults"]["labelStyle"] = "ribbon"
        with self.assertRaisesRegex(ProjectError, "labelStyle"):
            validate_project(self.data, self.path)


if __name__ == "__main__":
    unittest.main()
