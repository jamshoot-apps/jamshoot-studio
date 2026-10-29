"""Studio's editor page, packaged assets and pattern tiles over HTTP."""

import json
import re
import unittest
from collections.abc import Iterator
from importlib.resources import files
from importlib.resources.abc import Traversable
from urllib.parse import urlencode, urljoin

from jamshoot.core.appearance import (
    GRADIENT_DEFAULTS,
    LAYOUT_DEFAULTS,
    PATTERN_DEFAULTS,
    STARTER_PALETTES,
    STYLE_DEFAULTS,
    layout_defaults,
)
from jamshoot.render.background import render_background
from jamshoot.render.export import png_bytes
from studio_case import TOKEN, StudioCase

ASSET_TYPES = {"css": "text/css", "js": "javascript"}


def resource_paths(root: Traversable, prefix: str = "") -> Iterator[str]:
    """Paths of packaged files under ``root``, skipping ``vendor`` folders."""
    for item in root.iterdir():
        name = prefix + item.name
        if item.is_file():
            yield name
        elif item.name != "vendor":
            yield from resource_paths(item, name + "/")


class StudioPageTests(StudioCase):
    """The editor page, its packaged assets and the pattern tiles it shows."""

    def test_studio_serves_packaged_accessible_ui_and_no_external_dependencies(self):
        """The editor is served under a self-only CSP and links only packaged files."""
        status, headers, body = self.client.request(self.editor, token=None)
        self.assertEqual(status, 200)
        self.assertIn("text/html", headers["Content-Type"])
        html = body.decode()
        for text in ("JamShoot", "<label", "Preview", "Save", "Export", TOKEN):
            self.assertIn(text, html)
        self.assertNotIn("https://", html)
        self.assertIn("default-src 'self'", headers["Content-Security-Policy"])
        linked = set(re.findall(r'(?:href|src)="/([^" ]+\.(?:css|js))"', html))
        self.assertIn("shared/styles/theme.css", linked)
        for asset in resource_paths(files("jamshoot").joinpath("web")):
            mime = ASSET_TYPES.get(asset.rpartition(".")[2])
            if mime is None:
                continue
            linked.discard(asset)
            status, headers, body = self.client.request("/" + asset, token=None)
            self.assertEqual(status, 200, asset)
            self.assertIn(mime, headers["Content-Type"])
            self.assertTrue(body)
        self.assertEqual(linked, set(), "The page links files the package does not ship")
        self.assertIn('src="/assets/jamshoot-logo.svg"', html)
        status, headers, body = self.client.request("/assets/jamshoot-logo.svg", token=None)
        self.assertEqual(status, 200)
        self.assertIn("image/svg+xml", headers["Content-Type"])
        self.assertNotIn(b"<script", body)

    def test_page_asset_graph_resolves_nested_imports_and_stylesheet_urls(self):
        """Links from both pages reach every packaged JS, CSS and SVG file."""
        pending = ["/", self.editor]
        visited: set[str] = set()
        patterns = {
            "js": r'\bfrom\s+"([^"]+)"',
            "css": r'url\("([^"]+)"\)',
        }
        while pending:
            path = pending.pop()
            if path in visited:
                continue
            visited.add(path)
            status, headers, body = self.client.request(path, token=None)
            self.assertEqual(status, 200, path)
            suffix = path.rpartition(".")[2]
            if suffix in ASSET_TYPES:
                self.assertIn(ASSET_TYPES[suffix], headers["Content-Type"], path)
            pattern = patterns.get(suffix, r'(?:href|src)="([^" ]+\.(?:css|js|svg))"')
            pending.extend(urljoin(path, ref) for ref in re.findall(pattern, body.decode()))
        shipped = {
            "/" + path
            for path in resource_paths(files("jamshoot").joinpath("web"))
            if path.rpartition(".")[2] in {"js", "css", "svg"}
        }
        self.assertLessEqual(shipped, visited, "An asset is unreachable from both pages")

    def test_appearance_catalog_and_pattern_tiles_use_packaged_pillow_renderer(self):
        """Tiles match the export renderer, with optional color overrides from the query."""
        snapshot = self.client.json(f"{self.api}/project")[1]
        appearance = snapshot["appearance"]
        self.assertEqual(appearance["starterPalettes"], STARTER_PALETTES)
        self.assertEqual(appearance["styleDefaults"], STYLE_DEFAULTS)
        self.assertEqual(appearance["patternDefaults"], PATTERN_DEFAULTS)
        self.assertEqual(appearance["gradientDefaults"], GRADIENT_DEFAULTS)
        targets = {target["id"]: target for target in snapshot["catalog"]["targets"]}
        mac, phone = targets["appstore.mac.1280x800"], targets["appstore.iphone.1179x2556"]
        self.assertEqual((mac["autoLayout"], phone["autoLayout"]), ("window-top", "device-top"))
        self.assertIn("window-top", mac["layouts"])
        self.assertNotIn("window-top", phone["layouts"])
        self.assertNotIn("window-top", phone["layoutDefaults"])
        self.assertEqual(phone["layoutDefaults"]["device-top"], LAYOUT_DEFAULTS)
        self.assertEqual(
            mac["layoutDefaults"]["device-focus"], layout_defaults("device-focus", (1280, 800))
        )
        for pattern in snapshot["schema"]["$defs"]["pattern"]["enum"]:
            status, headers, content = self.client.request(
                f"/pattern-preview/{pattern}", token=None
            )
            self.assertEqual(status, 200)
            self.assertIn("image/png", headers["Content-Type"])
            style = {"pattern": pattern, "seed": "preview"}
            self.assertEqual(content, png_bytes(render_background((160, 96), style)))
        self.assertEqual(self.client.request("/pattern-preview/unknown").status, 404)
        status, _, content = self.client.request(
            "/pattern-preview/dots?top=112233&bottom=445566&accent=AABBCC&seed=s1", token=None
        )
        self.assertEqual(status, 200)
        colors = {"top": "#112233", "bottom": "#445566", "accent": "#aabbcc"}
        style = {"pattern": "dots", "seed": "s1", "colors": colors}
        self.assertEqual(content, png_bytes(render_background((160, 96), style)))
        self.assertEqual(self.client.request("/pattern-preview/dots?top=red").status, 400)
        self.assertEqual(self.client.request("/features/appearance/background.js").status, 200)

    def test_pattern_tiles_use_the_entire_allowed_seed(self):
        """Seeds up to the schema's text limit match the export renderer; longer ones fail."""
        limit = self.client.json(f"{self.api}/project")[1]["schema"]["$defs"]["text"]["maxLength"]
        contents = []
        for seed in ("a" * (limit - 1) + "1", "a" * (limit - 1) + "2", "🌿" * limit):
            status, _, content = self.client.request(
                "/pattern-preview/dots?" + urlencode({"seed": seed}), token=None
            )
            self.assertEqual(status, 200)
            with render_background((160, 96), {"pattern": "dots", "seed": seed}) as image:
                self.assertEqual(content, png_bytes(image))
            contents.append(content)
        self.assertNotEqual(contents[0], contents[1])
        self.assertEqual(
            self.client.request("/pattern-preview/dots?seed=" + "a" * (limit + 1)).status, 400
        )

    def test_editor_exposes_independent_panels_and_explicit_slide_navigation(self):
        """Both side panels have ``aria-controls`` toggles; slides are an ordered list."""
        elements = self.page().elements
        for panel in ("slides-panel", "inspector-panel"):
            self.assertEqual(elements[panel][0], "aside")
            toggle = elements["toggle-" + panel][1]
            self.assertEqual(toggle["aria-controls"], panel)
            self.assertIn("aria-expanded", toggle)
        self.assertEqual(elements["slides"][0], "ol")
        self.assertNotIn("slide", elements)
        self.assertEqual(elements["upload"][1]["class"], "sr-only")
        self.assertEqual(self.client.request("/../server.py").status, 404)
        self.assertEqual(self.client.request("/fonts.ttf").status, 404)

    def test_icons_and_license_are_served_locally_without_widening_static_access(self):
        """Only icons listed in the vendor manifest are served, byte for byte."""
        self.assertEqual(self.client.request("/shared/ui/icon/icon.css", token=None).status, 200)
        root = files("jamshoot").joinpath("web", "vendor", "ionicons")
        manifest = json.loads(root.joinpath("manifest.json").read_text())
        for name in manifest["files"]:
            with self.subTest(asset=name):
                status, headers, body = self.client.request("/vendor/ionicons/" + name, token=None)
                self.assertEqual(status, 200)
                self.assertEqual(body, root.joinpath(name).read_bytes())
                self.assertIn(
                    "image/svg+xml" if name.endswith(".svg") else "text/plain",
                    headers["Content-Type"],
                )
                self.assertIn("img-src 'self' blob:", headers["Content-Security-Policy"])
        for path in (
            "/vendor/ionicons/missing.svg",
            "/vendor/ionicons/../../server.py",
            "/vendor/ionicons/index.html",
            "/vendor/other/LICENSE",
            "/vendor/ionicons/manifest.json",
            "/index.html",
            "/home.html",
            "/editor/missing.js",
            "/editor/../index.html",
            "/editor/../../server/assets.py",
            "/styles/../vendor/ionicons/manifest.json",
            "/assets/../index.html",
            "/styles/icons.css/extra",
            "/pages/editor/editor.html",
            "/pages/home/home.html",
            "/shared/ui/select/missing.js",
            "/features/appearance/../../../server/assets.py",
            "/pages/editor/../../vendor/ionicons/manifest.json",
        ):
            self.assertEqual(self.client.request(path, token=None).status, 404)

    def test_global_controls_are_outside_active_slide_inspector(self):
        """Project-wide controls are in the project dialog, slide controls in the inspector."""
        elements = self.page().elements
        self.assertEqual(elements["project-settings"][0], "dialog")
        self.assertEqual(elements["open-project"][1]["aria-controls"], "project-settings")
        for control in (
            "project-title",
            "target-options",
            "project-json",
            "output-path",
            "default-pattern",
            "default-saved-styles",
            "palette-editor",
            "default-customize-colors",
            "color-style-manager",
            "palette-list",
            "new-palette",
            "default-seed",
        ):
            ancestors = elements[control][2]
            self.assertIn("project-settings", ancestors)
            self.assertNotIn("inspector-panel", ancestors)
        for control in (
            "pattern",
            "saved-styles",
            "palette",
            "save-palette",
            "customize-colors",
            "asset-platform",
            "seed",
            "layout",
            "deviceFrame",
            "screenshotFit",
            "headline",
            "upload",
            "reset-style",
        ):
            self.assertIn("inspector-panel", elements[control][2])
        for control in ("variant", "undo", "redo"):
            self.assertIn("workspace", elements[control][2])
        for control in ("project-undo", "project-redo"):
            self.assertIn("project-settings", elements[control][2])
        for control in ("add-slide", "duplicate-slide", "remove-slide"):
            self.assertIn("slides-panel", elements[control][2])
        self.assertNotIn("color-preview", elements)
        self.assertNotIn("style-name", elements)
        self.assertEqual(elements["colors"][0], "fieldset")


if __name__ == "__main__":
    unittest.main()
