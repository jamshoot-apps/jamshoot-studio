"""Studio's project API: edit, plan, preview, save, export and assets."""

import copy
import hashlib
import io
import json
import unittest

from PIL import Image

from jamshoot.core.planning import plan_project
from jamshoot.core.project import load_project, validate_project
from jamshoot.render.compositor import render_job
from jamshoot.render.export import png_bytes
from studio_case import StudioCase
from support import BRAND_COLORS


class StudioProjectApiTests(StudioCase):
    """Studio project routes, which render with the same pipeline as the CLI."""

    def test_snapshot_exposes_the_custom_canvas_pixel_limit(self):
        """The snapshot reports the custom canvas pixel limit that validation uses."""
        status, snapshot = self.client.json(f"{self.api}/project")
        self.assertEqual(status, 200)
        self.assertEqual(snapshot["catalog"]["customMaxPixels"], 24_000_000)

    def test_invalid_draft_returns_field_errors_without_overwriting_the_project(self):
        """Save and plan return 400 with the field's JSON pointer and leave the file as is."""
        _, snapshot = self.client.json(f"{self.api}/project")
        before = self.path.read_bytes()
        snapshot["project"]["slides"][0]["name"] = "x" * 201
        for route in ("project", "plan"):
            with self.subTest(route=route):
                status, result = self.client.json(f"{self.api}/{route}", "POST", snapshot)
                self.assertEqual(status, 400)
                self.assertEqual(result["error"]["code"], "invalid_project")
                self.assertEqual(result["error"]["details"][0]["path"], "/slides/0/name")
                self.assertEqual(
                    result["error"]["details"][0]["message"], "Use at most 200 characters."
                )
                self.assertEqual(self.path.read_bytes(), before)

    def test_blank_headline_reports_actionable_guidance_and_preserves_saved_text(self):
        """A blank headline returns 400 for that field and leaves the file as is."""
        _, snapshot = self.client.json(f"{self.api}/project")
        before = self.path.read_bytes()
        snapshot["project"]["slides"][0]["copy"]["en-US"]["headline"] = " \t "
        status, result = self.client.json(f"{self.api}/project", "POST", snapshot)
        self.assertEqual(status, 400)
        self.assertEqual(
            result["error"]["details"],
            [
                {
                    "path": "/slides/0/copy/en-US/headline",
                    "message": "Enter text containing at least one non-space character.",
                }
            ],
        )
        self.assertEqual(self.path.read_bytes(), before)

    def test_http_edit_plan_preview_save_export_happy_path_uses_same_renderer(self):
        """Preview leaves the file as is; saved and exported pixels match it."""
        status, initial = self.client.json(f"{self.api}/project")
        self.assertEqual(status, 200)
        draft = copy.deepcopy(initial["project"])
        draft["slides"][0]["copy"]["en-US"]["headline"] = "Made in the studio"
        status, plan = self.client.json(f"{self.api}/plan", "POST", {"project": draft})
        self.assertEqual((status, plan["fileCount"]), (200, 1))
        status, headers, preview = self.client.request(
            f"{self.api}/preview", "POST", {"project": draft, "index": 0}
        )
        self.assertEqual(status, 200)
        self.assertIn("image/png", headers["Content-Type"])
        with Image.open(io.BytesIO(preview)) as image:
            self.assertEqual(image.size, (1280, 800))
            self.assertEqual(image.mode, "RGB")
        self.assertNotIn("Made in the studio", self.path.read_text())
        status, saved = self.client.json(
            f"{self.api}/project", "POST", {"project": draft, "revision": initial["revision"]}
        )
        self.assertEqual(status, 200)
        self.assertNotEqual(initial["revision"], saved["revision"])
        reference = render_job(plan_project(load_project(self.path))["files"][0])
        with Image.open(io.BytesIO(preview)) as image:
            self.assertEqual(image.tobytes(), reference.tobytes())
        status, manifest = self.client.json(f"{self.api}/export", "POST", {"project": draft})
        self.assertEqual((status, manifest["fileCount"]), (200, 1))
        output = self.root / "output" / manifest["files"][0]["output"]
        self.assertEqual(output.read_bytes(), preview)
        self.assertEqual(manifest["files"][0]["sha256"], hashlib.sha256(preview).hexdigest())

    def test_full_previews_carry_their_guides(self):
        """Full previews send guide boxes for the canvas and text; thumbnails send none."""
        _, initial = self.client.json(f"{self.api}/project")
        body = {"project": initial["project"], "index": 0}
        _, headers, _ = self.client.request(f"{self.api}/preview", "POST", body)
        guides = json.loads(headers["X-Jamshoot-Guides"])
        self.assertEqual(guides["canvas"], [1280, 800])
        self.assertIn("headline", guides["copy"])
        _, headers, _ = self.client.request(
            f"{self.api}/preview", "POST", body | {"thumbnail": True}
        )
        self.assertNotIn("X-Jamshoot-Guides", headers)

    def test_thumbnail_preview_is_the_downscaled_render(self):
        """A thumbnail is the full render scaled to fit 480x960."""
        _, initial = self.client.json(f"{self.api}/project")
        body = {"project": initial["project"], "index": 0, "thumbnail": True}
        status, _, thumbnail = self.client.request(f"{self.api}/preview", "POST", body)
        self.assertEqual(status, 200)
        reference = render_job(plan_project(load_project(self.path))["files"][0])
        reference.thumbnail((480, 960))
        with Image.open(io.BytesIO(thumbnail)) as image:
            self.assertEqual(image.size, (480, 300))
            self.assertEqual(image.tobytes(), reference.tobytes())
        body["thumbnail"] = "yes"
        self.assertEqual(self.client.request(f"{self.api}/preview", "POST", body).status, 400)

    def test_custom_appearance_preview_save_and_export_preserve_identical_pixels(self):
        """Slide colors and pattern settings survive save; preview and export pixels match."""
        snapshot = self.client.json(f"{self.api}/project")[1]
        data = snapshot["project"]
        data["slides"][0]["style"] = {
            "pattern": "hexagons",
            "colors": {"accent": "#cc3344", "top": "#f8eedd"},
            "patternSettings": {"opacity": 35, "rotation": 20, "density": 65},
        }
        expected = png_bytes(
            render_job(plan_project(validate_project(data, self.path))["files"][0])
        )
        self.assertEqual(self.preview(data), expected)
        status, saved = self.client.json(
            f"{self.api}/project", "POST", {"project": data, "revision": snapshot["revision"]}
        )
        self.assertEqual(status, 200)
        self.assertEqual(saved["project"], data)
        self.assertEqual(self.exported(data), [expected])

    def test_saved_color_styles_survive_http_save_reload_preview_and_export(self):
        """A saved color style survives save and reload; preview and export pixels match."""
        _, snapshot = self.client.json(f"{self.api}/project")
        data = snapshot["project"]
        data["colorStyles"] = [{"id": "brand", "name": "Бренд / Spring", "colors": BRAND_COLORS}]
        data["defaults"]["colorStyle"] = "brand"
        status, saved = self.client.json(
            f"{self.api}/project", "POST", {"project": data, "revision": snapshot["revision"]}
        )
        self.assertEqual(status, 200)
        self.assertEqual(saved["project"], data)
        self.assertEqual(self.client.json(f"{self.api}/project")[1]["project"], data)
        expected = png_bytes(
            render_job(plan_project(validate_project(data, self.path))["files"][0])
        )
        self.assertEqual(self.preview(data), expected)
        self.assertEqual(self.exported(data), [expected])
        self.assertEqual(self.client.request("/features/appearance/palettes.js").status, 200)

    def test_independent_slide_patterns_round_trip_and_export_their_previews(self):
        """Each slide keeps its own pattern and seed through save and export."""
        _, initial = self.client.json(f"{self.api}/project")
        draft = copy.deepcopy(initial["project"])
        second = copy.deepcopy(draft["slides"][0])
        second["id"] = "second"
        draft["slides"].append(second)
        draft["slides"][0]["style"] = {"pattern": "waves", "seed": "first"}
        draft["slides"][1]["style"] = {"pattern": "grid", "seed": "second"}
        status, plan = self.client.json(f"{self.api}/plan", "POST", {"project": draft})
        self.assertEqual((status, plan.get("fileCount")), (200, 2))
        self.assertEqual([job["pattern"] for job in plan["files"]], ["waves", "grid"])
        previews = [self.preview(draft, index) for index in range(2)]
        self.assertNotEqual(previews[0], previews[1])
        save = {"project": draft, "revision": initial["revision"]}
        self.assertEqual(self.client.json(f"{self.api}/project", "POST", save)[0], 200)
        self.assertEqual(self.client.json(f"{self.api}/project")[1]["project"], draft)
        self.assertEqual(self.exported(draft), previews)

    def test_mobile_settings_preview_save_and_export_share_exact_pixels(self):
        """iPhone and iPad targets preview at their sizes and export the same bytes."""
        _, initial = self.client.json(f"{self.api}/project")
        elements = self.page().elements
        for control in ("target-options", "deviceFrame", "screenshotFit", "asset-platform"):
            self.assertIn(control, elements)
        draft = initial["project"]
        draft["targets"] = ["appstore.iphone.1206x2622", "appstore.ipad.2752x2064"]
        draft["defaults"].update(layout="auto", deviceFrame="silver", screenshotFit="contain")
        for platform in ("iphone", "ipad"):
            draft["slides"][0]["assets"][platform] = "assets/screenshot.png"
        save = {"project": draft, "revision": initial["revision"]}
        self.assertEqual(self.client.json(f"{self.api}/project", "POST", save)[0], 200)
        previews = []
        for index, size in enumerate(((1206, 2622), (2752, 2064))):
            previews.append(self.preview(draft, index))
            with Image.open(io.BytesIO(previews[-1])) as image:
                self.assertEqual((image.size, image.mode), (size, "RGB"))
        self.assertEqual(self.exported(draft), previews)

    def test_repeated_exports_create_new_batches_and_preserve_previous_files(self):
        """A second export goes to ``output-2`` and leaves the first batch untouched."""
        initial = self.client.json(f"{self.api}/project")[1]
        first_status, first = self.client.json(f"{self.api}/export", "POST", initial)
        self.assertEqual(first_status, 200)
        first_path = self.root / "output"
        before = (first_path / "manifest.json").read_bytes()
        initial["project"]["slides"][0]["copy"]["en-US"]["headline"] = "Another export"
        status, result = self.client.json(f"{self.api}/export", "POST", initial)
        self.assertEqual(status, 200)
        self.assertEqual(result["outputDirectory"], str(self.root / "output-2"))
        self.assertEqual(first["outputDirectory"], str(first_path))
        self.assertEqual((first_path / "manifest.json").read_bytes(), before)
        self.assertTrue((self.root / "output-2" / "manifest.json").is_file())

    def test_save_rejects_external_edit_and_exports_keep_previous_batches(self):
        """Saving over a file changed on disk is a conflict; exports still succeed."""
        _, initial = self.client.json(f"{self.api}/project")
        self.path.write_text(self.path.read_text() + "\n")
        self.assertEqual(self.client.json(f"{self.api}/project", "POST", initial)[0], 409)
        self.assertEqual(self.client.json(f"{self.api}/export", "POST", initial)[0], 200)
        self.assertEqual(self.client.json(f"{self.api}/export", "POST", initial)[0], 200)

    def test_asset_library_lists_local_images_without_external_symlinks(self):
        """Only regular image files in ``assets`` are listed, and only with the token."""
        assets = self.path.parent / "assets"
        Image.new("RGB", (16, 12), "red").save(assets / "CullBit viewer.png")
        (assets / "notes.txt").write_text("private")
        outside = self.root / "outside.png"
        Image.new("RGB", (1, 1)).save(outside)
        try:
            (assets / "escape.png").symlink_to(outside)
        except OSError:
            pass
        status, result = self.client.json(f"{self.api}/assets")
        self.assertEqual(status, 200)
        self.assertEqual(
            [item["path"] for item in result["assets"]],
            ["assets/CullBit viewer.png", "assets/screenshot.png"],
        )
        self.assertEqual(self.client.request(f"{self.api}/assets", token=None).status, 403)
        data = self.client.json(f"{self.api}/project")[1]
        data["project"]["slides"][0]["name"] = "CullBit · Library"
        self.assertEqual(self.client.json(f"{self.api}/project", "POST", data)[0], 200)
        self.assertEqual(
            self.client.json(f"{self.api}/project")[1]["project"]["slides"][0]["name"],
            "CullBit · Library",
        )

    def test_upload_is_decoded_and_stored_as_a_safe_png_named_after_the_file(self):
        """Uploads become PNGs with portable names, numbered when taken; bad data gets 400."""
        image = io.BytesIO()
        Image.new("RGBA", (50, 40), "blue").save(image, "PNG")
        names = []
        for name in ("Home%20Screen.jpg", "Home%20Screen.jpg", "..%2F..%2Fevil.png", ""):
            status, payload = self.client.json(
                f"{self.api}/assets?name={name}", "POST", image.getvalue(), content_type="image/png"
            )
            self.assertEqual(status, 201)
            asset = (self.path.parent / payload["path"]).resolve()
            self.assertTrue(asset.is_relative_to(self.path.parent / "assets"))
            self.assertTrue(asset.is_file())
            names.append(payload["path"])
        self.assertEqual(
            names,
            [
                "assets/Home-Screen.png",
                "assets/Home-Screen-2.png",
                "assets/evil.png",
                "assets/screenshot-2.png",
            ],
        )
        status, _ = self.client.json(f"{self.api}/assets", "POST", b"bad", content_type="image/png")
        self.assertEqual(status, 400)


if __name__ == "__main__":
    unittest.main()
