"""Mobile and custom-size targets: catalog, planning, validation and frames."""

import copy
import json
import unittest

from PIL import Image, ImageDraw

from jamshoot.catalog import load_catalog
from jamshoot.core.planning import plan_project
from jamshoot.core.project import ProjectError, require_screenshots, validate_project
from jamshoot.core.starter import init_project
from jamshoot.render.compositor import PLACEHOLDER, render_job
from jamshoot.render.devices import DUO_FINISHES, GLASS, PALETTES, SPECS, DeviceStyle, render_device
from jamshoot.render.export import render_project
from support import run_jamshoot, temporary_directory


def rgb_colors(image: Image.Image) -> set[tuple[int, ...]]:
    """Every distinct RGB color of ``image``, ignoring alpha."""
    colors = image.convert("RGB").getcolors(image.width * image.height) or []
    return {color for _, color in colors if isinstance(color, tuple)}


def rgb(image: Image.Image, xy: tuple[int, int]) -> tuple[int, ...]:
    """The RGB color of one pixel."""
    value = image.convert("RGB").getpixel(xy)
    assert isinstance(value, tuple)
    return value


class MobileTests(unittest.TestCase):
    """iPhone, Duo and iPad targets: catalog, planning, validation and frames."""

    def setUp(self):
        self.root = temporary_directory(self)
        self.path = init_project(self.root / "project")
        self.data = json.loads(self.path.read_text())
        self.data["defaults"]["layout"] = "auto"
        self.data["slides"][0]["copy"]["en-US"] = {"headline": "Make space"}
        for platform, size in (
            ("iphone", (300, 650)),
            ("iphone-duo", (420, 600)),
            ("ipad", (450, 600)),
        ):
            Image.new("RGB", size, "#e63b63").save(self.path.parent / f"assets/{platform}.png")
            self.data["slides"][0]["assets"][platform] = f"assets/{platform}.png"

    def project(self):
        """``self.data`` validated against the project folder."""
        return validate_project(self.data, self.path)

    def test_catalog_matches_apple_pairs_including_legacy_status_bar_exceptions(self):
        """Catalog sizes, hardware, orientation and required groups match Apple's list."""
        catalog = load_catalog()
        duo_portraits = {(1398, 2034), (2007, 2853)}
        iphone_portraits = {
            (1260, 2736),
            (1290, 2796),
            (1320, 2868),
            (1284, 2778),
            (1242, 2688),
            (1179, 2556),
            (1206, 2622),
            (1170, 2532),
            (1125, 2436),
            (1080, 2340),
            (1242, 2208),
            (750, 1334),
        }
        ipad_portraits = {
            (2064, 2752),
            (2048, 2732),
            (1488, 2266),
            (1668, 2420),
            (1668, 2388),
            (1640, 2360),
            (1668, 2224),
        }
        expected = {
            # Duo has its own screenshot platform; its ids keep the appstore.iphone prefix.
            "iphone-duo": duo_portraits | {(h, w) for w, h in duo_portraits},
            "iphone": iphone_portraits
            | {(h, w) for w, h in iphone_portraits}
            | {
                (640, 1096),
                (640, 1136),
                (1136, 600),
                (1136, 640),
                (640, 920),
                (640, 960),
                (960, 600),
                (960, 640),
            },
            "ipad": ipad_portraits
            | {(h, w) for w, h in ipad_portraits}
            | {
                (1536, 2008),
                (1536, 2048),
                (2048, 1496),
                (2048, 1536),
                (768, 1004),
                (768, 1024),
                (1024, 748),
                (1024, 768),
            },
        }
        for platform, sizes in expected.items():
            targets = [t for t in catalog["targets"] if t["platform"] == platform]
            self.assertEqual({(t["width"], t["height"]) for t in targets}, sizes)
            for target in targets:
                self.assertTrue(target["displayGroups"])
                self.assertIn(target["hardware"], set(SPECS))
                if platform == "iphone-duo":
                    outer = "iphone-duo-outer" in target["displayGroups"]
                    self.assertEqual(target["hardware"], "duo-outer" if outer else "duo-inner")
                self.assertEqual(
                    target["orientation"],
                    "portrait" if target["height"] > target["width"] else "landscape",
                )
        self.assertEqual(len(catalog["targets"]), 62)
        self.assertEqual(len({t["id"] for t in catalog["targets"]}), 62)
        required = {g["id"] for g in catalog["displayGroups"] if g.get("required")}
        self.assertEqual(required, {"iphone-island-medium", "ipad-13"})
        self.assertEqual(catalog["reviewedAt"], "2026-10-15")

    def test_auto_plans_mixed_platforms_with_localized_assets_and_variant_settings(self):
        """``auto`` uses a window on Mac and a device elsewhere; variants override frame and fit."""
        self.data["targets"] = [
            "appstore.mac.1280x800",
            "appstore.iphone.1206x2622",
            "appstore.ipad.2752x2064",
        ]
        self.data["variants"] = [
            {"id": "dark", "deviceFrame": "black"},
            {"id": "light", "deviceFrame": "silver", "screenshotFit": "cover"},
        ]
        before = copy.deepcopy(self.data)
        plan = plan_project(self.project())
        self.assertEqual(plan["fileCount"], 6)
        self.assertEqual(
            [job["layout"] for job in plan["files"][:3]], ["window-top", "device-top", "device-top"]
        )
        self.assertEqual([job["platform"] for job in plan["files"][:3]], ["mac", "iphone", "ipad"])
        self.assertEqual(plan["files"][1]["hardware"], "island")
        self.assertEqual(plan["files"][1]["screenshotFit"], "contain")
        self.assertEqual(plan["files"][4]["deviceFrame"], "silver")
        self.assertEqual(plan["files"][4]["screenshotFit"], "cover")
        self.assertTrue(plan["files"][2]["source"].endswith("assets/ipad.png"))
        self.assertEqual(self.data, before)

    def test_duo_sizes_use_their_own_screenshot_in_a_device(self):
        """Duo sizes plan device layouts with the Duo screenshot, which must exist."""
        self.data["targets"] = ["appstore.iphone.1398x2034", "appstore.iphone.2853x2007"]
        files = plan_project(self.project())["files"]
        self.assertEqual([job["platform"] for job in files], ["iphone-duo", "iphone-duo"])
        self.assertEqual({job["layout"] for job in files}, {"device-top"})
        self.assertTrue(all(job["source"].endswith("assets/iphone-duo.png") for job in files))
        del self.data["slides"][0]["assets"]["iphone-duo"]
        with self.assertRaisesRegex(ProjectError, "no Duo screenshot"):
            require_screenshots(self.project())

    def test_validation_rejects_incompatible_layouts_missing_assets_and_frame_typos(self):
        """Window layouts on iPhone, unknown frames or fits, and missing screenshots fail."""
        self.data["targets"] = ["appstore.iphone.1206x2622"]
        self.project()
        for section, key, value, expected in (
            ("defaults", "layout", "window-top", "incompatible"),
            ("defaults", "deviceFrame", "gold", "deviceFrame"),
            ("defaults", "screenshotFit", "stretch", "screenshotFit"),
        ):
            invalid = copy.deepcopy(self.data)
            invalid[section][key] = value
            with self.assertRaisesRegex(ProjectError, expected):
                validate_project(invalid, self.path)
        del self.data["slides"][0]["assets"]["iphone"]
        with self.assertRaisesRegex(ProjectError, "no iPhone screenshot"):
            require_screenshots(self.project())

    def test_custom_sizes_render_the_screenshot_without_a_mockup(self):
        """``custom.<w>x<h>`` renders the screenshot unframed at that size; bad sizes fail."""
        Image.new("RGB", (400, 300), "#e63b63").save(self.path.parent / "assets/custom.png")
        self.data["slides"][0]["assets"]["custom"] = "assets/custom.png"
        self.data["targets"] = ["custom.1080x1920"]
        job = plan_project(self.project())["files"][0]
        self.assertEqual((job["platform"], job["layout"]), ("custom", "device-top"))
        self.assertTrue(job["output"].endswith("custom.1080x1920/01-overview.png"))
        with render_job(job) as image:
            self.assertEqual(image.size, (1080, 1920))
            colors = rgb_colors(image)
        self.assertIn((230, 59, 99), colors, "The screenshot is drawn as is")
        self.assertFalse({(0, 0, 0), (17, 17, 17)} & colors, "No device frame is drawn")
        for target in ("custom.10x1920", "custom.1080x9000", "custom.1080", "custom.0x100"):
            self.data["targets"] = [target]
            with self.assertRaisesRegex(ProjectError, "unknown target"):
                self.project()

    def test_missing_screenshots_preview_as_blank_screens_but_block_export(self):
        """A target without its screenshot previews a placeholder; export fails before writing."""
        self.data["targets"] = ["appstore.ipad.2064x2752"]
        del self.data["slides"][0]["assets"]["ipad"]
        project = self.project()
        job = plan_project(project)["files"][0]
        self.assertIsNone(job["source"])
        with render_job(job) as image:
            self.assertEqual(image.size, (2064, 2752))
            self.assertIn(PLACEHOLDER, rgb_colors(image))
        output = self.root / "out"
        with self.assertRaisesRegex(ProjectError, "Slide 1 \\(overview\\): no iPad screenshot"):
            render_project(project, output)
        self.assertFalse(output.exists())

    def test_all_mobile_sizes_render_exact_rgb_with_devices_in_both_orientations(self):
        """Every mobile catalog size renders RGB at its size with the screenshot centered."""
        self.data["targets"] = [
            t["id"]
            for t in load_catalog()["targets"]
            if t["platform"] in {"iphone", "iphone-duo", "ipad"}
        ]
        self.assertEqual(len(self.data["targets"]), 58)
        for job in plan_project(self.project())["files"]:
            with self.subTest(target=job["target"]):
                with render_job(job) as image:
                    self.assertEqual(image.mode, "RGB")
                    self.assertEqual(image.size, (job["width"], job["height"]))
                    self.assertEqual(
                        image.getpixel((image.width // 2, int(image.height * 0.65))), (230, 59, 99)
                    )

    def test_device_focus_keeps_large_tablet_screenshot_and_strict_platform_validation(self):
        """Device focus enlarges an iPad screenshot; Mac renders at size; iPhone rejects windows."""
        self.data["targets"] = ["appstore.ipad.2732x2048"]
        # A landscape screenshot keeps a landscape device; orientation follows the screenshot.
        Image.new("RGB", (600, 450), "#e63b63").save(self.path.parent / "assets/ipad.png")
        self.data["defaults"].update(
            layout="device-focus", deviceFrame="none", screenshotFit="cover"
        )
        job = plan_project(self.project())["files"][0]
        with render_job(job) as image:
            # The source fills a much larger area than the balanced layout.
            self.assertEqual(image.size, (2732, 2048))
            self.assertEqual(image.getpixel((1366, 650)), (230, 59, 99))
            self.assertEqual(image.getpixel((400, 1600)), (230, 59, 99))
        self.data["targets"] = ["appstore.mac.1280x800"]
        with render_job(plan_project(self.project())["files"][0]) as image:
            # Mac device layouts draw a MacBook around the unchanged screenshot.
            self.assertEqual(image.size, (1280, 800))
        self.data["targets"] = ["appstore.iphone.1206x2622"]
        self.data["defaults"]["layout"] = "window-top"
        with self.assertRaisesRegex(ProjectError, "incompatible"):
            self.project()

    def test_device_frames_preserve_screenshot_edges_and_landscape_orientation(self):
        """Frames keep contained screenshots uncropped, follow orientation and differ by fit."""
        source = Image.new("RGB", (300, 600), "red")
        draw = ImageDraw.Draw(source)
        draw.rectangle((0, 0, 299, 69), fill="lime")
        draw.rectangle((0, 530, 299, 599), fill="blue")
        for hardware in SPECS:
            for frame in ("black", "silver", "none"):
                style = DeviceStyle(hardware, frame, "contain")
                image = render_device(source, (300, 650), (260, 500), style)
                self.assertEqual(image.mode, "RGBA")
                self.assertLessEqual(image.width, 260)
                self.assertLessEqual(image.height, 500)
                colors = rgb_colors(image)
                self.assertTrue({(0, 255, 0), (0, 0, 255), (255, 0, 0)} <= colors)
        landscape = source.rotate(90, expand=True)
        image = render_device(
            landscape, (650, 300), (500, 260), DeviceStyle("island", "silver", "contain")
        )
        self.assertGreater(image.width, image.height)
        self.assertEqual(rgb(image, (int(image.width * 0.1), image.height // 2)), (0, 255, 0))
        self.assertEqual(rgb(image, (int(image.width * 0.9), image.height // 2)), (0, 0, 255))
        contained, covered = (
            render_device(source, (300, 300), (300, 300), DeviceStyle("plain", "none", fit))
            for fit in ("contain", "cover")
        )
        self.assertNotEqual(contained.tobytes(), covered.tobytes())
        # Fit adapts the screen to the screenshot instead of letterboxing or cropping it.
        self.assertAlmostEqual(contained.width / contained.height, 0.5, delta=0.01)
        self.assertEqual(covered.size, (300, 300))
        for hardware, platform in (("island", "iphone"), ("tablet", "ipad"), ("home", "ipad")):
            style = DeviceStyle(hardware, "black", "contain", platform)
            framed = render_device(source, (1290, 2796), (400, 400), style)
            colors = rgb_colors(framed)
            self.assertTrue({(0, 255, 0), (0, 0, 255)} <= colors, hardware)
        laptop = render_device(
            landscape, (2880, 1800), (640, 460), DeviceStyle("plain", "silver", "contain", "mac")
        )
        self.assertGreater(laptop.width, laptop.height)
        self.assertTrue(laptop.width <= 640 and laptop.height <= 460)

    def test_duo_frames_follow_apples_drawings(self):
        """Outer Duo: round trailing-top camera, square spine. Inner Duo: no camera or hinge."""

        def top_edge(image: Image.Image, fraction: float) -> int:
            """The first opaque row in the column at ``fraction`` of the width."""
            x = int(image.width * fraction)
            column = image.getchannel("A").crop((x, 0, x + 1, image.height))
            bbox = column.point([0] * 129 + [255] * 127).getbbox()
            assert bbox is not None
            return bbox[1]

        def row(image: Image.Image, y: int, width: int) -> bytes:
            """The RGB bytes of the first ``width`` pixels of row ``y``."""
            return image.convert("RGB").crop((0, y, width, y + 1)).tobytes()

        outer = render_device(
            Image.new("RGB", (1398, 2034), "red"),
            (1398, 2034),
            (700, 1000),
            DeviceStyle("duo-outer", "silver", "contain"),
        )
        top = outer.convert("RGB").crop((0, 0, outer.width, outer.height // 4)).tobytes()
        glass = bytes(GLASS["island"])
        camera = [
            (index // 3 % outer.width, index // 3 // outer.width)
            for index in range(0, len(top), 3)
            if top[index : index + 3] == glass
        ]
        xs, ys = [x for x, _ in camera], [y for _, y in camera]
        self.assertGreater(min(xs), outer.width * 0.75, "The camera sits at the trailing edge")
        self.assertLess(max(ys), outer.height * 0.2, "The camera sits at the top")
        width, height = max(xs) - min(xs), max(ys) - min(ys)
        self.assertAlmostEqual(width / height, 1, delta=0.1, msg="The camera is round")
        # The hinge spine is square; the trailing corners are round.
        self.assertGreater(top_edge(outer, 0.97) - top_edge(outer, 0.03), outer.height * 0.02)
        self.assertAlmostEqual(outer.height / outer.width, 117.8 / 84.1, delta=0.06)

        inner = render_device(
            Image.new("RGB", (2007, 2853), "red"),
            (2007, 2853),
            (700, 1000),
            DeviceStyle("duo-inner", "silver", "contain"),
        )
        self.assertNotIn(GLASS["island"], rgb_colors(inner), "The camera is under the display")
        # No hinge: the side band at the fold matches the band away from it.
        band = inner.width // 8
        self.assertEqual(row(inner, inner.height // 2, band), row(inner, inner.height // 3, band))
        middle = top_edge(inner, 0.5)
        for fraction in (0.03, 0.97):
            self.assertGreater(top_edge(inner, fraction) - middle, inner.height * 0.01)

    def test_closed_duo_hinge_has_rounded_ends_and_stays_inside_the_output(self):
        """The closed Duo's hinge has rounded, shaded ends and fits the requested size."""
        for finish in ("black", "silver"):
            for size in ((180, 260), (700, 1000)):
                with self.subTest(finish=finish, size=size):
                    image = render_device(
                        Image.new("RGB", (1398, 2034), "red"),
                        (1398, 2034),
                        size,
                        DeviceStyle("duo-outer", finish, "contain"),
                    )
                    self.assertLessEqual(image.width, size[0])
                    self.assertLessEqual(image.height, size[1])
                    alpha = image.getchannel("A")
                    middle = image.height // 2
                    silhouette = alpha.crop((0, middle, image.width, middle + 1)).getbbox()
                    assert silhouette is not None
                    left = silhouette[0]
                    # The barrel's curved cap starts below the front half's top edge.
                    cap = alpha.crop((left, 0, left + 1, image.height)).getbbox()
                    glass = alpha.crop(
                        (image.width // 10, 0, image.width // 10 + 1, image.height)
                    ).getbbox()
                    assert cap is not None and glass is not None
                    self.assertGreater(cap[1], glass[1])
                    self.assertLess(cap[3], glass[3])
                    shades = rgb_colors(
                        image.crop((left, middle, left + max(3, image.width // 50), middle + 1))
                    )
                    self.assertGreater(len(shades), 1, "The barrel has a curved metal highlight")

    def test_duo_hinge_join_is_square_while_its_outer_corners_are_round(self):
        """The outer Duo's body edge stays solid up to the hinge at its top and bottom."""
        image = render_device(
            Image.new("RGB", (1398, 2034), "red"),
            (1398, 2034),
            (700, 1000),
            DeviceStyle("duo-outer", "silver", "contain"),
        )
        screen = image.getchannel("R").point([0] * 255 + [255]).getbbox()
        assert screen is not None
        unit = screen[2] - screen[0]
        body_left = screen[0] - round(SPECS["duo-outer"].bezels.side * unit)
        top = screen[1] - round(SPECS["duo-outer"].bezels.top * unit)
        inset = round(0.012 * unit)
        alpha = image.getchannel("A")
        for y in (top + inset, image.height - inset - 1):
            self.assertEqual(alpha.getpixel((body_left - 1, y)), 255)
            self.assertEqual(alpha.getpixel((body_left - round(0.028 * unit), y)), 0)

    def test_duo_finishes_share_geometry_and_do_not_recolor_other_devices(self):
        """Finishes share one silhouette; only Duo frames use the Duo band colors."""
        for hardware in ("duo-outer", "duo-inner", "island", "tablet", "plain"):
            images = []
            for finish in ("black", "silver"):
                platform = "mac" if hardware == "plain" else None
                image = render_device(
                    Image.new("RGB", (1398, 2034), "red"),
                    (1398, 2034),
                    (700, 1000),
                    DeviceStyle(hardware, finish, "contain", platform),
                )
                images.append(image)
                colors = rgb_colors(image)
                self.assertIn(PALETTES[finish]["bezel"], colors)
                if hardware.startswith("duo-"):
                    self.assertIn(DUO_FINISHES[finish]["band"], colors)
                    self.assertNotIn(PALETTES[finish]["band"], colors)
                else:
                    self.assertIn(PALETTES[finish]["band"], colors)
                    self.assertNotIn(DUO_FINISHES[finish]["band"], colors)
            self.assertEqual(
                images[0].getchannel("A").tobytes(), images[1].getchannel("A").tobytes()
            )

    def test_macbook_camera_housing_matches_apples_front_view_proportions(self):
        """The camera housing is about 12% of the screen width wide and 2.2% of it deep."""
        for frame in ("black", "silver"):
            for size in ((500, 350), (1000, 700)):
                image = render_device(
                    Image.new("RGB", (3024, 1964), "red"),
                    (3024, 1964),
                    size,
                    DeviceStyle("plain", frame, "cover", "mac"),
                )
                screen = image.getchannel("R").point([0] * 255 + [255]).getbbox()
                assert screen is not None
                left, top, right, _ = screen
                width = right - left
                housing = image.getchannel("R").point([255] * 255 + [0])
                housing = housing.crop((left + width // 4, top + 2, right - width // 4, top + 3))
                bounds = housing.getbbox()
                assert bounds is not None
                self.assertAlmostEqual((bounds[2] - bounds[0]) / width, 0.122, delta=0.01)
                column = image.getchannel("R").crop(
                    ((left + right) // 2, top, (left + right) // 2 + 1, image.height)
                )
                visible = column.point([0] * 255 + [255]).getbbox()
                assert visible is not None
                self.assertAlmostEqual(visible[1] / width, 0.022, delta=0.005)

    def test_macbook_lower_bezel_has_no_thumb_groove_mask_artifacts(self):
        """The bezel below the screen is one solid color at every width."""
        for finish in ("black", "silver"):
            for width in (500, 650, 701, 1000):
                image = render_device(
                    Image.new("RGB", (3024, 1964), "red"),
                    (3024, 1964),
                    (width, 700),
                    DeviceStyle("plain", finish, "cover", "mac"),
                )
                screen = image.getchannel("R").point([0] * 255 + [255]).getbbox()
                assert screen is not None
                left, _, right, bottom = screen
                chin = image.crop((left, bottom + 1, right, bottom + 3))
                self.assertEqual(rgb_colors(chin), {PALETTES[finish]["bezel"]})

    def test_cli_mobile_render_happy_path_and_font_free_raw(self):
        """``render --json`` writes each target at its size; ``raw`` puts the screenshot at 0,0."""
        self.data["targets"] = ["appstore.iphone.1206x2622", "appstore.ipad.2064x2752"]
        self.data["defaults"].update(deviceFrame="silver", screenshotFit="contain")
        self.path.write_text(json.dumps(self.data))
        result = run_jamshoot("render", self.path, "--out", self.root / "out", "--json")
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        manifest = json.loads(result.stdout)
        self.assertEqual(manifest["fileCount"], 2)
        for item in manifest["files"]:
            with Image.open(self.root / "out" / item["output"]) as image:
                self.assertEqual(image.size, (item["width"], item["height"]))
        self.data["defaults"]["layout"] = "raw"
        with render_job(plan_project(self.project())["files"][0]) as image:
            self.assertEqual(image.getpixel((0, 0)), (230, 59, 99))
