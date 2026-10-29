"""Renderer: backgrounds, text fitting, image loading, composition and export."""

import hashlib
import json
import random
import unittest

from PIL import Image, ImageDraw

from jamshoot.catalog import load_catalog
from jamshoot.core.planning import plan_project
from jamshoot.core.project import ProjectError, load_project, load_schema
from jamshoot.core.starter import init_project
from jamshoot.render.background import render_background
from jamshoot.render.compositor import render_job
from jamshoot.render.export import render_project
from jamshoot.render.images import load_image
from jamshoot.render.text import fit_text
from support import run_jamshoot, temporary_directory


class RenderTests(unittest.TestCase):
    """Backgrounds, text fitting, image loading, composition and batch export."""

    def setUp(self):
        self.root = temporary_directory(self)
        self.path = init_project(self.root / "project")
        self.data = json.loads(self.path.read_text())
        Image.new("RGB", (640, 400), "#e63b63").save(self.path.parent / "assets/screenshot.png")

    def project(self):
        """Save ``self.data`` and load it as a validated project."""
        self.path.write_text(json.dumps(self.data), encoding="utf-8")
        return load_project(self.path)

    def test_every_pattern_is_distinct_seeded_and_does_not_touch_global_random(self):
        """Patterns are deterministic per seed, distinct, and leave global ``random`` alone."""
        state = random.getstate()
        fingerprints = []
        for pattern in load_schema()["$defs"]["pattern"]["enum"]:
            with self.subTest(pattern=pattern):
                style = {"pattern": pattern, "seed": "launch"}
                first = render_background((320, 200), style)
                self.assertEqual(first.mode, "RGB")
                self.assertEqual(first.tobytes(), render_background((320, 200), style).tobytes())
                fingerprints.append(hashlib.sha256(first.tobytes()).hexdigest())
        self.assertEqual(len(set(fingerprints)), len(fingerprints))
        self.assertEqual(random.getstate(), state)
        confetti = [
            render_background((320, 200), {"pattern": "confetti", "seed": seed})
            for seed in ("a", "b")
        ]
        self.assertNotEqual(confetti[0].tobytes(), confetti[1].tobytes())

    def test_text_wraps_latin_cyrillic_and_long_words_and_rejects_overflow(self):
        """Text wraps within its box; overflow and unsupported scripts raise ProjectError."""
        draw = ImageDraw.Draw(Image.new("RGB", (400, 160)))
        for text in ("A useful app for everyone", "Удобное приложение", "x" * 45):
            font, wrapped = fit_text(text, (360, 130), max_size=44, min_size=18)
            bounds = draw.multiline_textbbox((0, 0), wrapped, font=font, spacing=6)
            self.assertLessEqual(bounds[2] - bounds[0], 360)
            self.assertLessEqual(bounds[3] - bounds[1], 130)
        with self.assertRaisesRegex(ProjectError, "overflow"):
            fit_text("word " * 400, (100, 30), max_size=32, min_size=24)
        with self.assertRaisesRegex(ProjectError, "unsupported|Unsupported"):
            fit_text("مرحبا", (360, 130), max_size=44, min_size=18)

    def test_image_loader_applies_orientation_flattens_alpha_and_rejects_bad_inputs(self):
        """``load_image`` applies EXIF rotation, flattens alpha onto white and rejects bad input."""
        transparent = self.root / "transparent.png"
        Image.new("RGBA", (30, 20), (255, 0, 0, 0)).save(transparent)
        image = load_image(transparent)
        self.assertEqual(image.mode, "RGB")
        self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
        photo = Image.new("RGB", (30, 20), "red")
        exif = Image.Exif()
        exif[274] = 6
        photo.save(self.root / "rotated.jpg", exif=exif)
        self.assertEqual(load_image(self.root / "rotated.jpg").size, (20, 30))
        transparent.write_bytes(b"not a PNG")
        with self.assertRaisesRegex(ProjectError, "image"):
            load_image(transparent)
        Image.new("RGB", (30, 20)).save(transparent)
        with self.assertRaisesRegex(ProjectError, "limit"):
            load_image(transparent, max_pixels=500)

    def test_compositor_renders_all_mac_sizes_rgb_and_raw_preserves_source(self):
        """Every Mac size renders RGB with the screenshot; ``raw`` fills the canvas with it."""
        self.data["targets"] = [
            item["id"] for item in load_catalog()["targets"] if item["platform"] == "mac"
        ]
        self.data["slides"][0]["copy"]["en-US"] = {
            "headline": "Your app at a glance",
            "subtitle": "Clear, focused and local",
            "featureLabel": "EXAMPLE APP",
        }
        for job in plan_project(self.project())["files"]:
            with self.subTest(target=job["target"]):
                image = render_job(job)
                self.assertEqual(image.size, (job["width"], job["height"]))
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(
                    image.getpixel((image.width // 2, int(image.height * 0.7))), (230, 59, 99)
                )
        self.data["defaults"]["layout"] = "raw"
        raw = render_job(plan_project(self.project())["files"][0])
        self.assertEqual(raw.getpixel((0, 0)), (230, 59, 99))
        self.assertEqual(raw.getpixel((1279, 799)), (230, 59, 99))

    def test_export_writes_stable_manifest_hashes_refuses_existing_and_rolls_back_failure(self):
        """Exports are reproducible, refuse an existing folder and leave nothing on failure."""
        self.data["variants"] = [
            {"id": "a"},
            {"id": "b", "colors": {"top": "#181c28", "bottom": "#252938"}},
        ]
        project = self.project()
        first = render_project(project, self.root / "out")
        second = render_project(project, self.root / "again")
        self.assertEqual(first, second)
        self.assertEqual(first["fileCount"], 2)
        self.assertEqual(json.loads((self.root / "out/manifest.json").read_text()), first)
        for item in first["files"]:
            image_path = self.root / "out" / item["output"]
            self.assertEqual(item["sha256"], hashlib.sha256(image_path.read_bytes()).hexdigest())
            with Image.open(image_path) as image:
                self.assertEqual(image.mode, "RGB")
                self.assertEqual(image.format, "PNG")
                self.assertEqual(image.size, (item["width"], item["height"]))
        with self.assertRaisesRegex(ProjectError, "exist"):
            render_project(project, self.root / "out")
        self.data["variants"][1]["seed"] = "different"
        self.data["slides"].append(
            {
                "id": "broken",
                "assets": {"mac": "assets/broken.png"},
                "copy": {"en-US": {"headline": "Broken"}},
            }
        )
        (self.path.parent / "assets/broken.png").write_bytes(b"broken")
        with self.assertRaises(ProjectError):
            render_project(self.project(), self.root / "failed")
        self.assertFalse((self.root / "failed").exists())
        self.assertEqual(sorted(p.name for p in self.root.iterdir()), ["again", "out", "project"])

    def test_cli_init_validate_plan_render_happy_path_and_json_failure(self):
        """``render --json`` prints its files, then a JSON error for an existing folder."""
        command = ("render", self.path, "--out", self.root / "output", "--json")
        result = run_jamshoot(*command, cwd=self.root)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(json.loads(result.stdout)["fileCount"], 1)
        self.assertEqual(result.stderr, "")
        again = run_jamshoot(*command, cwd=self.root)
        self.assertEqual(again.returncode, 1)
        self.assertIn("exist", json.loads(again.stdout)["error"]["message"])
        self.assertEqual(again.stderr, "")

    def test_export_limit_and_text_errors_leave_no_output(self):
        """File-limit and text-overflow errors fail before an output folder exists."""
        with self.assertRaisesRegex(ProjectError, "limit"):
            render_project(self.project(), self.root / "limited", max_files=0)
        self.data["slides"][0]["copy"]["en-US"]["headline"] = "word " * 399
        with self.assertRaisesRegex(ProjectError, "overflow"):
            render_project(self.project(), self.root / "overflow")
        self.assertEqual([p.name for p in self.root.iterdir()], ["project"])
