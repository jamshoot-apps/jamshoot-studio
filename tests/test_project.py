"""The project schema, semantic validation and planning."""

import copy
import json
import tempfile
import unittest
from importlib.resources import files
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

from jamshoot.core.planning import plan_project
from jamshoot.core.project import ProjectError, load_project, require_screenshots
from support import temporary_directory


class ProjectContractTests(unittest.TestCase):
    """The project schema, semantic validation and deterministic planning."""

    def setUp(self):
        self.root = temporary_directory(self)
        (self.root / "screen.png").write_bytes(b"fixture; decoding belongs to the renderer")
        self.path = self.root / "project.json"
        self.data: dict[str, Any] = {
            "version": 1,
            "project": {"name": "Пример"},
            "targets": ["appstore.mac.1280x800", "appstore.mac.1440x900"],
            "locales": ["en-US", "ru"],
            "defaults": {
                "layout": "window-top",
                "pattern": "dots",
                "seed": "launch",
            },
            "slides": [
                {
                    "id": "overview",
                    "copy": {"en-US": {"headline": "Overview"}, "ru": {"headline": "Обзор"}},
                    "assets": {"mac": "screen.png"},
                },
                {
                    "id": "details",
                    "copy": {"en-US": {"headline": "Details"}, "ru": {"headline": "Детали"}},
                    "assets": {"mac": {"en-US": "screen.png", "ru": "screen.png"}},
                },
            ],
            "variants": [{"id": "light"}, {"id": "dark", "colors": {"top": "#181c28"}}],
        }

    def load(self, data=None):
        """Write ``data`` (or ``self.data``) to project.json and load it."""
        self.path.write_text(json.dumps(self.data if data is None else data), encoding="utf-8")
        return load_project(self.path)

    def test_schema_is_packaged_valid_and_rejects_unknown_properties(self):
        """The packaged schema is valid Draft 2020-12 and rejects unknown keys."""
        schema = json.loads(files("jamshoot").joinpath("data", "project.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        validator = Draft202012Validator(schema)
        self.assertEqual(list(validator.iter_errors(self.data)), [])
        invalid = copy.deepcopy(self.data)
        invalid["slidez"] = []
        self.assertTrue(list(validator.iter_errors(invalid)))

    def test_happy_path_plans_every_requested_combination_in_stable_order(self):
        """Plans cover every variant, locale, target and slide in a stable order."""
        project = self.load()
        before = copy.deepcopy(project.data)
        plan = plan_project(project)
        self.assertEqual(plan, plan_project(project))
        self.assertEqual(project.data, before)
        self.assertEqual(plan["fileCount"], 16)
        self.assertEqual(len({item["output"] for item in plan["files"]}), 16)
        first = plan["files"][0]
        self.assertEqual(first["output"], "light/en-US/appstore.mac.1280x800/01-overview.png")
        self.assertEqual((first["width"], first["height"]), (1280, 800))
        self.assertEqual(first["headline"], "Overview")
        self.assertEqual(first["source"], str((self.root / "screen.png").resolve()))
        self.assertEqual(plan["files"][-1]["headline"], "Детали")
        self.assertFalse((self.root / "output").exists())

    def test_variant_omission_produces_one_default_variant(self):
        """Without variants a single ``default`` variant is planned."""
        del self.data["variants"]
        plan = plan_project(self.load())
        self.assertEqual(plan["fileCount"], 8)
        self.assertTrue(all(item["variant"] == "default" for item in plan["files"]))

    def test_slide_style_overrides_variants_without_changing_other_slides(self):
        """A slide style overrides defaults and variants for that slide only."""
        override = {
            "pattern": "waves",
            "seed": "slide-one",
            "deviceFrame": "silver",
            "screenshotFit": "cover",
        }
        self.data["slides"][0]["style"] = override
        before = copy.deepcopy(self.data)
        plan = plan_project(self.load())
        self.assertEqual(self.data, before)
        self.assertEqual(plan["fileCount"], 16)
        for job in plan["files"]:
            if job["slide"] == "overview":
                for key, value in override.items():
                    self.assertEqual(job[key], value)
            else:
                self.assertEqual(job["pattern"], "dots")
                self.assertEqual(job["seed"], "launch")
                dark = {"top": "#181c28"} if job["variant"] == "dark" else {}
                self.assertEqual(job.get("colors", {}), dark)
                self.assertEqual(job["deviceFrame"], "black")

    def test_slide_style_is_partial_and_strict(self):
        """A slide style may set any field subset; unknown keys or bad values fail."""
        self.data["slides"][0]["style"] = {"pattern": "grid"}
        self.load()
        overrides: list[Any] = [
            {"patern": "grid"},
            {"pattern": "unknown"},
            {"seed": ""},
            [],
            {"id": "x"},
        ]
        for override in overrides:
            with self.subTest(style=override):
                self.data["slides"][0]["style"] = override
                with self.assertRaisesRegex(ProjectError, "slides/0/style"):
                    self.load()

    def test_layout_validation_uses_effective_slide_style(self):
        """A slide style sets that slide's layout; any slide may use ``raw``."""
        # Mac screenshots render inside a MacBook frame in device layouts.
        self.data["slides"][0]["style"] = {"layout": "device-top"}
        plan = plan_project(self.load())["files"]
        self.assertEqual(
            {job["layout"] for job in plan if job["slide"] == "overview"}, {"device-top"}
        )
        for slide in self.data["slides"]:
            slide["style"] = {"layout": "raw"}
        self.assertTrue(all(job["layout"] == "raw" for job in plan_project(self.load())["files"]))

    def test_invalid_projects_fail_with_actionable_paths(self):
        """Errors point to the field or value that needs fixing."""
        cases = [
            (lambda d: d.update(version=2), "version"),
            (lambda d: d.update(version=True), "version"),
            (lambda d: d.update(typo=1), "typo"),
            (lambda d: d["defaults"].update(pattern="typo"), "pattern"),
            (lambda d: d["defaults"].update(layout="device-frame"), "layout"),
            (lambda d: d.update(targets=["unknown"]), "targets"),
            (lambda d: d["slides"][1].update(id="overview"), "id"),
            (lambda d: d["variants"][1].update(id="light"), "id"),
            (lambda d: d["slides"][0]["copy"].pop("ru"), "ru"),
            (lambda d: d["slides"][1]["assets"]["mac"].pop("ru"), "ru"),
            (lambda d: d["slides"][0].update(assets={}), "no Mac screenshot"),
            (lambda d: d["slides"][0].update(id="../escape"), "id"),
            (lambda d: d["slides"][0]["assets"].update(mac="absent.png"), "absent.png"),
        ]
        for mutate, expected in cases:
            with self.subTest(expected=expected):
                data = copy.deepcopy(self.data)
                mutate(data)
                with self.assertRaises(ProjectError) as error:
                    require_screenshots(self.load(data))
                self.assertIn(expected, str(error.exception))

    def test_assets_must_be_local_portable_paths_inside_project(self):
        """Absolute, drive, parent and URL asset paths are rejected."""
        for path in ("../outside.png", "/tmp/screen.png", "C:\\screen.png", "https://x.test/a.png"):
            with self.subTest(path=path):
                data = copy.deepcopy(self.data)
                data["slides"][0]["assets"]["mac"] = path
                with self.assertRaises(ProjectError):
                    self.load(data)

    def test_symlink_cannot_escape_project_directory(self):
        """An asset symlink pointing outside the project is rejected."""
        with tempfile.TemporaryDirectory() as outside:
            source = Path(outside) / "outside.png"
            source.write_bytes(b"outside")
            link = self.root / "link.png"
            try:
                link.symlink_to(source)
            except OSError:
                self.skipTest("Creating symlinks is not permitted on this host")
            self.data["slides"][0]["assets"]["mac"] = "link.png"
            with self.assertRaises(ProjectError):
                self.load()

    def test_ten_slide_store_limit_is_enforced(self):
        """Eleven slides fail; the App Store allows ten per set."""
        self.data["slides"] = [dict(self.data["slides"][0], id=f"slide-{i}") for i in range(11)]
        with self.assertRaises(ProjectError):
            self.load()

    def test_locales_reject_windows_device_names_with_extensions(self):
        """Locales named like Windows devices fail, with or without an extension."""
        for locale in ("CON.txt", "nul.png", "lpt1.foo", "AUX .txt"):
            with self.subTest(locale=locale):
                data = copy.deepcopy(self.data)
                data["locales"] = [locale]
                for slide in data["slides"]:
                    slide["copy"] = {locale: {"headline": "Overview"}}
                    slide["assets"] = {"mac": "screen.png"}
                with self.assertRaisesRegex(ProjectError, "locales/id:.*nonportable"):
                    self.load(data)

    def test_custom_targets_cannot_exceed_the_renderers_pixel_limit(self):
        """Custom canvases over the renderer's pixel limit fail to load."""
        data = copy.deepcopy(self.data)
        data["defaults"]["layout"] = "raw"
        data["targets"] = ["custom.6000x4000"]
        job = plan_project(self.load(data))["files"][0]
        self.assertEqual((job["width"], job["height"]), (6000, 4000))
        for target in ("custom.6000x4001", "custom.8192x8192"):
            with self.subTest(target=target):
                data["targets"] = [target]
                with self.assertRaisesRegex(ProjectError, "at most 24,000,000 pixels"):
                    self.load(data)

    def test_large_matrix_is_rejected_before_building_plan(self):
        """A plan over ``max_files`` fails before any job is built."""
        with self.assertRaisesRegex(ProjectError, "16.*8"):
            plan_project(self.load(), max_files=8)

    def test_duplicate_json_keys_and_nonfinite_numbers_are_rejected(self):
        """Duplicate keys and NaN are rejected rather than silently accepted."""
        for text in ('{"version":1,"version":2}', '{"version":NaN}'):
            with self.subTest(text=text):
                self.path.write_text(text)
                with self.assertRaises(ProjectError):
                    load_project(self.path)
