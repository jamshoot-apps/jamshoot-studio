"""Offline provenance and integration contracts for the vendored SVG subset."""

import hashlib
import json
import re
import unittest
from html.parser import HTMLParser
from importlib.resources import files
from urllib.parse import urljoin
from xml.etree import ElementTree


class IconElements(HTMLParser):
    """Attributes of every element with the ``icon`` class."""

    def __init__(self) -> None:
        super().__init__()
        self.icons: list[dict[str, str | None]] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if "icon" in (attributes.get("class") or "").split():
            self.icons.append(attributes)


class IconTests(unittest.TestCase):
    """Vendored Ionicons are pinned, unmodified and used only as decoration."""

    def test_vendored_icons_are_pinned_unmodified_svg_with_the_upstream_license(self):
        """Every icon matches its manifest hash, is inert SVG and ships with the license."""
        root = files("jamshoot").joinpath("web", "vendor", "ionicons")
        manifest = json.loads(root.joinpath("manifest.json").read_text())
        self.assertEqual(manifest["version"], "8.1.0")
        self.assertRegex(manifest["commit"], r"^[0-9a-f]{40}$")
        license_text = root.joinpath("LICENSE").read_text()
        self.assertIn("The MIT License", license_text)
        self.assertIn("Ionic", license_text)
        self.assertIn("permission notice shall be included", license_text)
        self.assertEqual(
            {item.name for item in root.iterdir()}, set(manifest["files"]) | {"manifest.json"}
        )
        for name, digest in manifest["files"].items():
            with self.subTest(asset=name):
                self.assertNotIn("/", name)
                content = root.joinpath(name).read_bytes()
                self.assertEqual(hashlib.sha256(content).hexdigest(), digest)
                if name == "LICENSE":
                    continue
                self.assertTrue(name.endswith("-outline.svg"))
                svg = ElementTree.fromstring(content)
                self.assertEqual(svg.tag, "{http://www.w3.org/2000/svg}svg")
                self.assertEqual(svg.attrib["viewBox"], "0 0 512 512")
                for element in svg.iter():
                    self.assertNotIn(
                        element.tag.rsplit("}", 1)[-1], {"script", "foreignObject", "image", "use"}
                    )
                    for attribute, value in element.attrib.items():
                        self.assertFalse(attribute.lower().startswith("on"))
                        self.assertNotIn("url(", value.lower())

    def test_ui_icons_are_local_decorative_and_replace_unicode_glyphs(self):
        """Icons are local and aria-hidden; buttons keep ``aria-label``s; no Unicode glyphs."""
        web = files("jamshoot").joinpath("web")
        css = web.joinpath("shared/ui/icon/icon.css").read_text()
        names = set(re.findall(r'url\("(/vendor/ionicons/[^"/]+\.svg)"\)', css))
        self.assertGreaterEqual(len(names), 10)
        for name in names:
            path = urljoin("/shared/ui/icon/icon.css", name).lstrip("/")
            self.assertTrue(web.joinpath(path).is_file(), name)
        html = web.joinpath("pages/editor/editor.html").read_text()
        parser = IconElements()
        parser.feed(html)
        self.assertGreaterEqual(len(parser.icons), 15)
        for icon in parser.icons:
            self.assertEqual(icon["aria-hidden"], "true")
            classes = str(icon["class"]).split()
            icon_name = next(name for name in classes if name.startswith("icon-"))
            self.assertIn(f".{icon_name} ", css)
        for glyph in ("×", "↑", "↓", "＋", "▤", "☷", "▧"):
            self.assertNotIn(glyph, html)
        self.assertIn('href="../../shared/ui/icon/icon.css"', html)
        for label in (
            "Hide slides panel",
            "Hide settings panel",
            "Move slide up",
            "Move slide down",
            "Delete slide",
            "Close project settings",
        ):
            self.assertIn(f'aria-label="{label}"', html)
