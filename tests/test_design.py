"""Studio's stylesheets follow its design system: tokens, layers, breakpoints and contrast."""

import re
import unittest
from collections.abc import Iterator
from pathlib import Path
from typing import cast

from PIL import ImageColor

from jamshoot.core.appearance import STARTER_PALETTES
from jamshoot.render.background import PAINTERS, render_background
from jamshoot.render.compositor import BADGE_FILL_ALPHA

WEB = Path(__file__).resolve().parents[1] / "src" / "jamshoot" / "web"
LAYERS = ("ds.reset", "ds.primitives", "ds.theme", "ds.base", "ds.components", "studio", "state")
# Layers that belong to one file: primitives, color roles and the overriding states.
OWNED_LAYERS = {"ds.primitives": "tokens.css", "ds.theme": "theme.css", "state": "base.css"}
BREAKPOINTS = {"34rem", "52rem", "64rem"}
Z_INDEX = {"var(--ds-layer-chrome)", "var(--ds-layer-top)", "auto"}
ROLES = (
    "bg",
    "surface",
    "surface-raised",
    "surface-sunken",
    "text",
    "text-muted",
    "text-faint",
    "accent",
    "accent-strong",
    "on-accent",
    "border",
    "border-strong",
)
# The color picker draws the value space it selects from, so its tracks are data.
PICKER_DATA = {"--studio-hue-track", "--studio-tone-plane"}
# Text, and the fills it sits on, in each palette (WCAG 2.2 AA).
TEXT = ("ds-text", "ds-text-muted", "ds-text-faint", "ds-accent", "studio-danger")
SURFACES = (
    "ds-bg",
    "ds-surface",
    "ds-surface-raised",
    "ds-surface-sunken",
    "studio-hover",
    "studio-selected",
    "studio-danger-surface",
)
# Non-text marks: control borders and the unsaved-changes dot need 3:1.
MARKS = ("ds-border-strong", "studio-warning")
# Properties one component or script sets on its own element; everything shared is a token.
LOCAL = {
    "--icon-svg",
    "--thumb-aspect",
    "--picker-color",
    "--picker-x",
    "--picker-y",
    "--picker-hue",
    "--picker-left",
    "--picker-top",
}

COMMENT = re.compile(r"/\*.*?\*/", re.S)
DECLARATION = re.compile(r"([-\w]+)\s*:\s*([^;{}]+);")
QUERY = re.compile(r"@(?:media|container)([^{]+)\{")
MEDIA_SCRIPT = re.compile(r"matchMedia\(\s*\"([^\"]+)\"\s*\)")
LENGTH = re.compile(r"(?<![-\w.#])(?![0.]+[a-z])\d*\.?\d+(px|r?em|ch|ex|pt|vmin|vmax|m?s)\b")
COLOR_FUNCTION = re.compile(r"\b(hsla?|hwb|lab|lch|oklab|oklch|color)\(")
RGB = re.compile(r"rgba?\(([^)]*)\)")
SHADING = re.compile(r"(0 0 0|255 255 255)( / [\d.]+)?")
WORD = re.compile(r"(?<![-\w#])[a-z]+(?![-\w(])", re.I)
USE = re.compile(r"var\((--[-\w]+)")
DEFINITION = re.compile(r"(--[-\w]+)\s*:")
SET = re.compile(r"setProperty\(\s*\"(--[-\w]+)\"")
GET = re.compile(r"getPropertyValue\(\s*\"(--[-\w]+)\"")
MIX = re.compile(r"color-mix\(in srgb, var\(--([-\w]+)\) (\d+)%, var\(--([-\w]+)\)\)")


def stylesheets() -> dict[str, str]:
    """Every stylesheet of the web UI, without comments."""
    return {path.name: COMMENT.sub("", path.read_text("utf-8")) for path in WEB.rglob("*.css")}


def declarations(css: str) -> Iterator[tuple[str, str]]:
    """``(property, value)`` pairs, with each ``url(...)`` removed from its value."""
    for prop, value in DECLARATION.findall(css):
        yield prop, re.sub(r"url\([^)]*\)", "", value).strip()


def top_level(css: str) -> Iterator[str]:
    """The prelude of every top-level statement or block."""
    depth, start = 0, 0
    for index, char in enumerate(css):
        if char == "{":
            if depth == 0:
                yield css[start:index].strip()
            depth += 1
        elif char == "}":
            depth -= 1
            start = index + 1
        elif char == ";" and depth == 0:
            yield css[start : index + 1].strip()
            start = index + 1


def block(css: str, start: int) -> str:
    """The contents of the first ``{...}`` block after ``start``."""
    opening = css.index("{", start)
    depth = 0
    for index in range(opening, len(css)):
        depth += {"{": 1, "}": -1}.get(css[index], 0)
        if depth == 0:
            return css[opening + 1 : index]
    raise ValueError("Unbalanced braces")


def palette(css: str) -> dict[str, str]:
    """Custom properties defined in ``css``, by name without the leading dashes."""
    return {prop[2:]: value.strip() for prop, value in DECLARATION.findall(css) if prop[:2] == "--"}


Color = tuple[float, float, float]


def blend(top: Color, under: Color, share: float) -> Color:
    """``top`` laid over ``under`` at ``share`` (0..1) coverage."""
    red, green, blue = (a * share + b * (1 - share) for a, b in zip(top, under, strict=True))
    return red, green, blue


def resolve(name: str, roles: dict[str, str], ground: str = "ds-surface") -> Color:
    """The opaque sRGB color (0..1) of role ``name``, composited over role ``ground``."""
    value = roles[name]
    if mix := MIX.fullmatch(value):
        first, weight, second = mix.groups()
        return blend(resolve(first, roles), resolve(second, roles), int(weight) / 100)
    if rgb := RGB.fullmatch(value):
        channels, _, alpha = rgb.group(1).partition("/")
        red, green, blue = (float(part) / 255 for part in channels.split())
        return blend((red, green, blue), resolve(ground, roles), float(alpha or 1))
    red, green, blue = ImageColor.getrgb(value)[:3]
    return red / 255, green / 255, blue / 255


def luminance(color: Color) -> float:
    """WCAG relative luminance of an sRGB color."""
    red, green, blue = (c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4 for c in color)
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue


def contrast(first: Color, second: Color) -> float:
    """WCAG contrast ratio of two opaque colors."""
    lighter, darker = sorted((luminance(first), luminance(second)), reverse=True)
    return (lighter + 0.05) / (darker + 0.05)


class DesignTokenTests(unittest.TestCase):
    """Studio's styles take colors, lengths, layers and motion from design tokens."""

    def setUp(self):
        self.sheets = stylesheets()

    def test_colors_are_roles_outside_the_palette(self):
        """Only theme.css sets colors; elsewhere a color is a role or black/white shading."""
        for name, css in self.sheets.items():
            if name == "theme.css":
                continue
            for prop, value in declarations(css):
                if prop in PICKER_DATA:
                    continue
                with self.subTest(sheet=name, property=prop):
                    self.assertNotRegex(value, r"#[0-9a-fA-F]{3,8}\b")
                    self.assertNotRegex(value, COLOR_FUNCTION)
                    for rgb in RGB.findall(value):
                        self.assertRegex(rgb, SHADING)
                    words = {word.lower() for word in WORD.findall(value)}
                    self.assertEqual(words & ImageColor.colormap.keys(), set())

    def test_lengths_and_durations_are_tokens(self):
        """Outside tokens.css, lengths and durations are tokens.

        Literal zero, %, fr, vw and vh are allowed.
        """
        for name, css in self.sheets.items():
            if name == "tokens.css":
                continue
            for prop, value in declarations(css):
                with self.subTest(sheet=name, property=prop):
                    self.assertIsNone(LENGTH.search(value), value)

    def test_stacking_uses_the_two_layers(self):
        """Every ``z-index`` is one of the two layer tokens or ``auto``."""
        for name, css in self.sheets.items():
            for prop, value in declarations(css):
                if prop == "z-index":
                    self.assertIn(value, Z_INDEX, name)

    def test_motion_uses_tokens_and_respects_reduced_motion(self):
        """Transitions use motion tokens; base.css and smooth scrolling honor reduced motion."""
        for name, css in self.sheets.items():
            for prop, value in declarations(css):
                if prop in {"transition", "animation"}:
                    self.assertIn("var(--ds-motion-", value, name)
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.sheets["base.css"])
        for script in WEB.rglob("*.js"):
            source = script.read_text("utf-8")
            if 'behavior: "smooth"' in source:
                self.assertIn("prefers-reduced-motion", source, script.name)

    def test_every_custom_property_used_is_defined(self):
        """Every ``var()`` and script-read property is defined; shared names are prefixed."""
        defined: set[str] = set()
        used: set[str] = set()
        for css in self.sheets.values():
            defined.update(DEFINITION.findall(css))
            used.update(USE.findall(css))
        for script in WEB.rglob("*.js"):
            text = script.read_text("utf-8")
            defined.update(SET.findall(text))
            used.update(GET.findall(text))
        self.assertEqual(used - defined, set())
        shared = {name for name in defined if name.startswith(("--ds-", "--studio-"))}
        self.assertEqual(defined - shared - LOCAL, set())


class DesignStructureTests(unittest.TestCase):
    """Cascade layers and breakpoints are the design system's fixed set."""

    def setUp(self):
        self.sheets = stylesheets()

    def test_tokens_declare_the_layer_order(self):
        """tokens.css declares the cascade layer order as its first statement."""
        statements = list(top_level(self.sheets["tokens.css"]))
        self.assertEqual(statements[0], f"@layer {', '.join(LAYERS)};")

    def test_every_rule_sits_in_its_layer(self):
        """Each top-level block is a known ``@layer``; owned layers stay in their file."""
        for name, css in self.sheets.items():
            for prelude in top_level(css):
                if prelude.endswith(";"):
                    continue
                with self.subTest(sheet=name, block=prelude):
                    layer = prelude.removeprefix("@layer ")
                    self.assertIn(layer, LAYERS)
                    self.assertEqual(OWNED_LAYERS.get(layer, name), name)

    def test_breakpoints_are_mobile_first(self):
        """CSS and script queries use only min-width at 34, 52 or 64rem."""
        queries = [query for css in self.sheets.values() for query in QUERY.findall(css)]
        for script in WEB.rglob("*.js"):
            queries += MEDIA_SCRIPT.findall(script.read_text("utf-8"))
        for query in queries:
            with self.subTest(query=query.strip()):
                self.assertNotRegex(query, r"max-width|width\s*[<>=]")
                for width in re.findall(r"min-width:\s*([^)]+)\)", query):
                    self.assertIn(width, BREAKPOINTS)


class DesignPaletteTests(unittest.TestCase):
    """Both palettes define every role and meet WCAG 2.2 AA."""

    def setUp(self):
        css = stylesheets()["theme.css"]
        dark = block(css, css.index("@media (prefers-color-scheme: dark)"))
        light = palette(css.replace(dark, ""))
        self.palettes = {"light": light, "dark": light | palette(dark)}

    def test_palettes_define_every_role_and_only_studio_extras(self):
        """Each palette defines every role; any other property is a ``studio-`` extra."""
        for scheme, roles in self.palettes.items():
            with self.subTest(scheme=scheme):
                self.assertEqual({f"ds-{role}" for role in ROLES} - set(roles), set())
                extras = {name for name in roles if not name.startswith("studio-")}
                self.assertEqual(extras - {f"ds-{role}" for role in ROLES}, set())

    def test_contrast(self):
        """Text is 4.5:1 on every surface, on-accent 4.5:1 on both accents, marks 3:1."""
        for scheme, roles in self.palettes.items():
            pairs = [(text, ground, 4.5) for text in TEXT for ground in SURFACES]
            pairs += [("ds-on-accent", accent, 4.5) for accent in ("ds-accent", "ds-accent-strong")]
            pairs += [(mark, ground, 3) for mark in MARKS for ground in SURFACES]
            for foreground, ground, minimum in pairs:
                with self.subTest(scheme=scheme, foreground=foreground, ground=ground):
                    ratio = contrast(resolve(foreground, roles, ground), resolve(ground, roles))
                    self.assertGreaterEqual(ratio, minimum)


class ScreenshotPaletteTests(unittest.TestCase):
    """Starter themes stay readable on every rendered background."""

    def test_text_and_badges_on_every_rendered_background_color(self):
        """Text, muted and accent (over the badge fill) reach 4.5:1 on every background color."""
        for name, roles in STARTER_PALETTES.items():
            accent = resolve("accent", roles)
            for pattern in ("none", *PAINTERS):
                image = render_background(
                    (240, 360), {"colors": roles, "pattern": pattern, "seed": "contrast"}
                )
                colors = cast(
                    list[tuple[int, tuple[int, int, int]]],
                    image.getcolors(image.width * image.height),
                )
                self.assertIsNotNone(colors)
                grounds = [(r / 255, g / 255, b / 255) for _, (r, g, b) in colors]
                for role in ("text", "muted", "accent"):
                    foreground = resolve(role, roles)
                    ratio = min(
                        contrast(
                            foreground,
                            (
                                blend(accent, ground, BADGE_FILL_ALPHA / 255)
                                if role == "accent"
                                else ground
                            ),
                        )
                        for ground in grounds
                    )
                    with self.subTest(palette=name, pattern=pattern, role=role):
                        self.assertGreaterEqual(ratio, 4.5)


if __name__ == "__main__":
    unittest.main()
