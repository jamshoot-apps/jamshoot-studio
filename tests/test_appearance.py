"""Appearance settings from schema to plan to rendered pixels."""

import copy
import json
import unittest
from typing import cast

from PIL import Image, ImageChops, ImageOps, ImageStat

from jamshoot.core.appearance import STARTER_PALETTES
from jamshoot.core.planning import plan_project
from jamshoot.core.project import ProjectError, load_schema, validate_project
from jamshoot.core.starter import init_project
from jamshoot.render.background import MESH_COLUMN, render_background
from jamshoot.render.compositor import render_job
from support import temporary_directory

SIZE = (320, 200)


def background(pattern: str, palette: str = "ocean", **style: object) -> bytes:
    """Pixel bytes of one background with seed ``a`` and extra style fields."""
    return render_background(
        SIZE, {"colors": STARTER_PALETTES[palette], "pattern": pattern, "seed": "a", **style}
    ).tobytes()


def rgb(image: Image.Image, xy: tuple[int, int]) -> tuple[int, ...]:
    """The red, green and blue channels of one pixel."""
    pixel = image.convert("RGB").getpixel(xy)
    if not isinstance(pixel, tuple):
        raise TypeError(f"Expected an RGB pixel, got {pixel!r}")
    return pixel


def distance(image: Image.Image, xy: tuple[int, int], expected: tuple[int, ...]) -> int:
    """Largest channel difference between the pixel at ``xy`` and the RGB color ``expected``."""
    return max(abs(a - b) for a, b in zip(rgb(image, xy), expected, strict=True))


class AppearanceTests(unittest.TestCase):
    """Themes, colors, gradients, patterns and glows from schema to pixels."""

    def setUp(self):
        self.path = init_project(temporary_directory(self) / "project")
        self.data = json.loads(self.path.read_text())

    def test_nested_options_merge_per_field_and_preserve_other_slides(self):
        """Colors and pattern settings merge per key; other slides keep the defaults."""
        self.data["defaults"].update(
            colors={"top": "#123456", "bottom": "#654321"},
            patternSettings={"density": 60, "opacity": 25},
        )
        self.data["variants"] = [{"id": "warm", "colors": {"accent": "#ff8800"}}]
        self.data["slides"].append(dict(copy.deepcopy(self.data["slides"][0]), id="second"))
        self.data["slides"][0]["style"] = {
            "colors": {"top": "#abcdef"},
            "patternSettings": {"scale": 150},
        }
        before = copy.deepcopy(self.data)
        plan = plan_project(validate_project(self.data, self.path))
        first, second = plan["files"]
        self.assertEqual(
            first["colors"], {"top": "#abcdef", "bottom": "#654321", "accent": "#ff8800"}
        )
        self.assertEqual(first["patternSettings"], {"density": 60, "opacity": 25, "scale": 150})
        self.assertEqual(second["colors"]["top"], "#123456")
        self.assertNotIn("scale", second["patternSettings"])
        self.assertEqual(self.data, before)

    def test_colors_and_pattern_options_are_strict_at_every_scope(self):
        """Invalid patterns, colors or settings raise ProjectError at every scope."""
        for invalid in (
            {"pattern": "blobs"},
            {"pattern": "organic"},
            {"colors": {"top": "red"}},
            {"colors": {"top": "#fff"}},
            {"colors": {"top": "#123456;"}},
            {"colors": {"unknown": "#123456"}},
            {"patternSettings": {"density": -1}},
            {"patternSettings": {"opacity": 101}},
            {"patternSettings": {"scale": 0}},
            {"patternSettings": {"rotation": 181}},
            {"patternSettings": {"strokeWidth": 7}},
            {"patternSettings": {"amplitude": True}},
            {"patternSettings": {"unknown": 1}},
            {"gradient": {"kind": "conic"}},
            {"gradient": {"angle": 361}},
            {"gradient": {"radius": 10}},
            {"gradient": {"midpoint": 100}},
            {"gradient": {"unknown": 1}},
        ):
            for scope in ("defaults", "variant", "slide"):
                data = copy.deepcopy(self.data)
                if scope == "defaults":
                    data["defaults"].update(invalid)
                elif scope == "variant":
                    data["variants"] = [{"id": "custom", **invalid}]
                else:
                    data["slides"][0]["style"] = invalid
                with self.subTest(invalid=invalid, scope=scope), self.assertRaises(ProjectError):
                    validate_project(data, self.path)

    def test_presets_and_patterns_are_distinct_and_match_schema(self):
        """Each starter palette paints a different background; the schema has 14 patterns."""
        schema = load_schema()["$defs"]
        self.assertEqual(len(STARTER_PALETTES), 8)
        self.assertEqual(len(schema["pattern"]["enum"]), 14)
        self.assertEqual(len({background("none", name) for name in STARTER_PALETTES}), 8)

    def test_custom_gradient_and_each_control_change_pixels_deterministically(self):
        """Custom colors set the gradient ends; each pattern control changes pixels repeatably."""
        custom = {"top": "#ff0000", "bottom": "#0000ff", "accent": "#00ff00"}
        style = {"pattern": "none", "seed": "a", "colors": custom}
        plain = render_background(SIZE, style)
        self.assertEqual(plain.getpixel((0, 0)), (255, 0, 0))
        self.assertEqual(plain.getpixel((0, 199)), (0, 0, 255))
        for pattern, key, value in (
            ("dots", "density", 85),
            ("dots", "scale", 180),
            ("dots", "opacity", 60),
            ("grid", "rotation", 30),
            ("circles", "strokeWidth", 4),
            ("waves", "amplitude", 90),
        ):
            with self.subTest(control=key):
                changed = background(pattern, patternSettings={key: value})
                self.assertNotEqual(background(pattern), changed)
                self.assertEqual(changed, background(pattern, patternSettings={key: value}))
        for key in ("density", "opacity"):
            self.assertEqual(background("dots", patternSettings={key: 0}), background("none"))

    def test_stops_color_the_gradient_in_position_order_and_hold_beyond_the_ends(self):
        """Stops apply in position order, end colors hold past the ends, and bad stops fail."""
        style = {"pattern": "none", "seed": "stops"}
        stops = [
            {"color": "#0000ff", "position": 80},
            {"color": "#ff0000", "position": 20},
            {"color": "#00ff00", "position": 50},
        ]
        gradient = {"angle": 90, "midpoint": 80, "stops": stops}
        image = render_background((256, 4), style | {"gradient": gradient}).convert("RGB")
        row = [cast(tuple[int, int, int], image.getpixel((x, 1))) for x in range(256)]
        self.assertEqual(row[10], (255, 0, 0), "Before the first stop its color holds")
        self.assertEqual(row[250], (0, 0, 255), "After the last stop its color holds")
        red, green, blue = row[128]
        self.assertTrue(green > 240 and red + blue < 10, "Stops apply in position order")
        red, green, _ = row[90]
        self.assertTrue(red > 0 and green > 0, "Neighboring stops blend")
        for invalid in (stops[:1], [{"color": "#000000", "position": 120}] * 2):
            with self.subTest(stops=invalid), self.assertRaises(ProjectError):
                validate_project(
                    self.data
                    | {"defaults": self.data["defaults"] | {"gradient": {"stops": invalid}}},
                    self.path,
                )

    def test_gradient_settings_shape_the_fill_and_defaults_keep_original_pixels(self):
        """The default is a linear two-color ramp; each setting reshapes it; ``solid`` is flat."""
        colors = {"top": "#ff0000", "bottom": "#0000ff"}
        style = {"pattern": "none", "seed": "a", "colors": colors}
        ramp = Image.linear_gradient("L").resize(SIZE)
        original = ImageOps.colorize(ramp, colors["top"], colors["bottom"])
        plain = render_background(SIZE, style)
        self.assertEqual(plain.convert("RGB").tobytes(), original.tobytes())
        explicit = style | {"gradient": {"kind": "linear", "angle": 180, "midpoint": 50}}
        self.assertEqual(render_background(SIZE, explicit).tobytes(), plain.tobytes())
        sideways = render_background(SIZE, style | {"gradient": {"angle": 90}})
        self.assertLessEqual(distance(sideways, (0, 100), (255, 0, 0)), 3)
        self.assertLessEqual(distance(sideways, (319, 100), (0, 0, 255)), 3)
        radial = {"kind": "radial", "centerX": 50, "centerY": 50}
        glow = render_background(SIZE, style | {"gradient": radial})
        self.assertLessEqual(distance(glow, (160, 100), (255, 0, 0)), 3)
        self.assertLessEqual(distance(glow, (0, 0), (0, 0, 255)), 3)
        for change in ({"radius": 60}, {"centerY": 0}, {"midpoint": 20}):
            with self.subTest(change=change):
                other = render_background(SIZE, style | {"gradient": radial | change})
                self.assertNotEqual(other.tobytes(), glow.tobytes())
        lighter = render_background(SIZE, style | {"gradient": {"midpoint": 80}})
        self.assertGreater(rgb(lighter, (0, 100))[0], rgb(plain, (0, 100))[0])
        solid = render_background(SIZE, style | {"gradient": {"kind": "solid"}})
        self.assertEqual(solid.convert("RGB").getcolors(), [(SIZE[0] * SIZE[1], (255, 0, 0))])

    def test_render_job_uses_custom_background_text_and_frame_colors(self):
        """Background, text, muted and frame colors appear in the rendered image."""
        self.data["slides"][0]["copy"]["en-US"]["subtitle"] = "Supporting text"
        self.data["defaults"].update(
            pattern="none",
            colors={
                "top": "#ffffff",
                "bottom": "#ffffff",
                "text": "#ff0000",
                "muted": "#00ff00",
                "frame": "#123456",
            },
        )
        job = plan_project(validate_project(self.data, self.path))["files"][0]
        image = render_job(job)
        self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))
        pixels = set(image.crop((0, 0, image.width, int(image.height * 0.35))).get_flattened_data())
        self.assertIn((255, 0, 0), pixels)
        self.assertIn((0, 255, 0), pixels)
        self.assertIn((18, 52, 86), set(image.get_flattened_data()))

    def test_rotated_pattern_reaches_every_corner(self):
        """A rotated pattern still covers every corner of portrait and landscape canvases."""
        style = {
            "pattern": "checkerboard",
            "seed": "rotation-edges",
            "colors": {"top": "#000000", "bottom": "#000000", "accent": "#ffffff"},
        }
        for width, height in ((320, 200), (200, 320)):
            for angle in (22, -18, 34, 90, 180):
                with self.subTest(size=(width, height), angle=angle):
                    image = render_background(
                        (width, height),
                        style
                        | {
                            "patternSettings": {
                                "rotation": angle,
                                "opacity": 100,
                                "scale": 40,
                                "density": 100,
                            }
                        },
                    )
                    for x, y in (
                        (0, 0),
                        (width - 32, 0),
                        (0, height - 32),
                        (width - 32, height - 32),
                    ):
                        patch = image.crop((x, y, x + 32, y + 32)).convert("L")
                        self.assertGreater(ImageStat.Stat(patch).mean[0] / 255, 0.2)

    def test_valid_extreme_settings_render_for_every_pattern_without_unbounded_geometry(self):
        """Extreme valid settings render RGB at the requested size for every pattern."""
        for pattern in load_schema()["$defs"]["pattern"]["enum"]:
            for settings in (
                {"density": 1e-100, "scale": 220},
                {
                    "density": 100,
                    "scale": 10,
                    "rotation": -180,
                    "strokeWidth": 6,
                    "amplitude": 100,
                },
            ):
                with self.subTest(pattern=pattern, settings=settings):
                    style = {"colors": STARTER_PALETTES["mint"], "pattern": pattern, "seed": "a"}
                    image = render_background(SIZE, style | {"patternSettings": settings})
                    self.assertEqual(image.size, SIZE)
                    self.assertEqual(image.mode, "RGB")

    def test_glows_light_their_area_and_leave_the_rest_of_the_fill(self):
        """A glow tints nearby pixels, fades with distance and may sit off the canvas."""
        black = {"top": "#000000", "bottom": "#000000"}
        style = {"pattern": "none", "seed": "a", "colors": black}
        glow = {"x": 0, "y": 0, "radius": 30, "color": "#ff0000", "opacity": 50, "blur": 5}
        image = render_background(SIZE, style | {"glows": [glow]})
        self.assertGreater(rgb(image, (2, 2))[0], 100)
        self.assertEqual(rgb(image, (2, 2))[1:], (0, 0))
        self.assertEqual(rgb(image, (SIZE[0] - 1, SIZE[1] - 1)), (0, 0, 0))
        self.assertLess(rgb(image, (90, 2))[0], rgb(image, (20, 2))[0])

        outside = render_background(SIZE, style | {"glows": [glow | {"x": -40, "y": 130}]})
        self.assertEqual(outside.size, SIZE)
        self.assertEqual(
            background("none", colors=black), background("none", colors=black, glows=[])
        )

    def test_glows_are_strict_and_a_slide_list_replaces_the_inherited_one(self):
        """A slide's ``glows`` replace the defaults' list; incomplete or out-of-range glows fail."""
        glow = {"x": 10, "y": 10, "radius": 20, "color": "#2f9bff", "opacity": 28, "blur": 8}
        self.data["defaults"]["glows"] = [glow, glow | {"x": 90}]
        self.data["slides"][0]["style"] = {"glows": [glow | {"color": "#ff7a1a"}]}
        plan = plan_project(validate_project(self.data, self.path))
        self.assertEqual(plan["files"][0]["glows"], [glow | {"color": "#ff7a1a"}])
        for broken in ({**glow, "blur": 31}, {k: v for k, v in glow.items() if k != "opacity"}):
            with self.subTest(glow=broken):
                self.data["defaults"]["glows"] = [broken]
                with self.assertRaises(ProjectError):
                    validate_project(self.data, self.path)

    def test_rotation_turns_the_same_pattern_instead_of_rebuilding_it(self):
        """A one-degree turn changes confetti only slightly instead of reshuffling it."""
        style = {
            "pattern": "confetti",
            "seed": "turn",
            "colors": {"top": "#000000", "bottom": "#000000", "accent": "#ffffff"},
        }

        def coverage(rotation: float) -> Image.Image:
            settings = {"opacity": 100, "rotation": rotation}
            return render_background(SIZE, style | {"patternSettings": settings}).convert("L")

        still, turned = coverage(0), coverage(1)
        difference = ImageStat.Stat(ImageChops.difference(still, turned)).mean[0]
        self.assertLess(difference, 0.05 * 255)

    def test_turned_dots_stay_whole_and_evenly_bright(self):
        """Rotated dots keep about the same count of full-brightness pixels."""

        def full_pixels(rotation: float) -> int:
            style = {
                "pattern": "dots",
                "seed": "even",
                "colors": {"top": "#000000", "bottom": "#000000", "accent": "#ffffff"},
                "patternSettings": {"opacity": 100, "rotation": rotation},
            }
            image = render_background((600, 900), style).convert("L")
            return image.histogram()[255]

        still = full_pixels(0)
        for angle in (17, 30, 45):
            with self.subTest(angle=angle):
                self.assertAlmostEqual(full_pixels(angle) / still, 1, delta=0.1)

    def test_density_spaces_shapes_without_resizing_them(self):
        """Doubling density quadruples dot coverage; doubling scale barely changes it."""

        def coverage(**settings: float) -> float:
            style = {
                "pattern": "dots",
                "seed": "size",
                "colors": {"top": "#000000", "bottom": "#000000", "accent": "#ffffff"},
                "patternSettings": {"opacity": 100, **settings},
            }
            image = render_background((900, 900), style).convert("L")
            return ImageStat.Stat(image).mean[0]

        self.assertAlmostEqual(coverage(density=100) / coverage(density=50), 4, delta=0.5)
        self.assertAlmostEqual(coverage(scale=200) / coverage(scale=100), 1, delta=0.25)

    def test_mesh_crosses_sharp_wave_rows_with_fainter_columns(self):
        """Mesh keeps the waves' full-brightness rows and adds dimmer vertical lines."""

        def histogram(pattern: str) -> list[int]:
            style = {
                "pattern": pattern,
                "seed": "mesh",
                "colors": {"top": "#000000", "bottom": "#000000", "accent": "#ffffff"},
                "patternSettings": {"opacity": 100, "amplitude": 0},
            }
            return render_background((600, 900), style).convert("L").histogram()

        waves, mesh = histogram("waves"), histogram("mesh")
        column = round(255 * MESH_COLUMN[2])
        # The seed's tilt antialiases edges; most row interiors must stay opaque.
        self.assertGreater(waves[255], 0.5 * sum(waves[1:]))
        self.assertGreaterEqual(mesh[255], 0.95 * waves[255])
        self.assertGreater(mesh[column], 0.25 * waves[255])
