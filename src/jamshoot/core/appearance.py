"""Appearance presets, defaults and layout rules; no Pillow or Studio imports."""

from collections.abc import Mapping
from typing import Any

# Text and badge accents meet WCAG AA across the gradient with default patterns.
# Keep dark gradients deep and pastel gradients light so pattern overlays stay readable.
# Studio offers these as starting points and copies the chosen one into the project.
STARTER_PALETTES = {
    "ocean": {
        "top": "#102f57",
        "bottom": "#103344",
        "accent": "#b4ecdf",
        "text": "#ffffff",
        "muted": "#d2e8e9",
        "frame": "#e7eef5",
    },
    "graphite": {
        "top": "#181c28",
        "bottom": "#252938",
        "accent": "#ddd2ff",
        "text": "#ffffff",
        "muted": "#d6d9e4",
        "frame": "#d7dce7",
    },
    "mint": {
        "top": "#e3f6ed",
        "bottom": "#b6dfcb",
        "accent": "#103e30",
        "text": "#143b30",
        "muted": "#214636",
        "frame": "#f5fbf8",
    },
    "sunset": {
        "top": "#402642",
        "bottom": "#522920",
        "accent": "#ffedcb",
        "text": "#fff8ee",
        "muted": "#ffeadf",
        "frame": "#f9e6e4",
    },
    "lavender": {
        "top": "#eee8ff",
        "bottom": "#cec8ed",
        "accent": "#352457",
        "text": "#302451",
        "muted": "#403258",
        "frame": "#f7f3ff",
    },
    "sand": {
        "top": "#fff3df",
        "bottom": "#ebd5af",
        "accent": "#4f3018",
        "text": "#49331e",
        "muted": "#523c26",
        "frame": "#fff9ef",
    },
    "rose": {
        "top": "#fce8ef",
        "bottom": "#f1c3ce",
        "accent": "#582036",
        "text": "#55233a",
        "muted": "#55283d",
        "frame": "#fff4f7",
    },
    "midnight": {
        "top": "#090d22",
        "bottom": "#1e204a",
        "accent": "#c8d1ff",
        "text": "#ffffff",
        "muted": "#d0d7ff",
        "frame": "#dce1f5",
    },
}

# Shared defaults for projects that omit pattern adjustments.
PATTERN_DEFAULTS = {
    "density": 50,
    "opacity": 48 / 255 * 100,
    "scale": 100,
    "rotation": 0,
    "strokeWidth": 1,
    "amplitude": 100 / 3,
}

# The original vertical top-to-bottom gradient. Angles follow CSS (180° points down);
# radial centers are % of the canvas and the radius is % of the farthest corner.
GRADIENT_DEFAULTS = {
    "kind": "linear",
    "angle": 180,
    "midpoint": 50,
    "centerX": 50,
    "centerY": 30,
    "radius": 100,
}

DEFAULT_PALETTE = "ocean"

# Text and screenshot geometry for portrait canvases: vertical spacing is % of the canvas
# height, widths % of its width. A nonzero ``screenshotTop`` pins where the screenshot's
# area starts instead of following the text.
LAYOUT_DEFAULTS = {
    "topMargin": 6.5,
    "labelGap": 1.4,
    "subtitleGap": 1.3,
    "textWidth": 82,
    "screenshotGap": 3.6,
    "screenshotTop": 0,
    "screenshotWidth": 84,
    "bottomMargin": 3,
}
# Landscape canvases have less height, so the same proportions of it read larger.
LANDSCAPE_LAYOUT = {
    "topMargin": 6,
    "labelGap": 1.8,
    "subtitleGap": 2.2,
    "textWidth": 72,
    "screenshotGap": 4,
    "screenshotWidth": 88,
    "bottomMargin": 3,
}
# Large device: compact text so the screenshot takes most of the canvas.
FOCUS_LAYOUT = {
    "topMargin": 4,
    "labelGap": 0.8,
    "subtitleGap": 0.9,
    "screenshotGap": 2.4,
    "screenshotWidth": 94,
    "bottomMargin": 2,
}

# Built-in text per field: size is % of the canvas height, line height % of the font size.
TYPOGRAPHY_DEFAULTS = {
    "featureLabel": {"size": 1.5, "weight": 450, "lineHeight": 116},
    "headline": {"size": 4.4, "weight": 700, "lineHeight": 116},
    "subtitle": {"size": 2.1, "weight": 450, "lineHeight": 116},
}
LANDSCAPE_TEXT_SIZES = {"featureLabel": 2.2, "headline": 5.6, "subtitle": 2.8}
FOCUS_TEXT_SIZES = {"featureLabel": 1.2, "headline": 3.4, "subtitle": 1.7}
TEXT_DEFAULTS = {"font": None, "letterSpacing": 0, "uppercase": False}


STYLE_DEFAULTS = {
    "deviceFrame": "black",
    "screenshotFit": "contain",
    "labelStyle": "text",
}


def auto_layout(target: Mapping[str, Any]) -> str:
    """The default layout for ``target``: ``window-top`` for Mac, otherwise ``device-top``."""
    return "window-top" if target["platform"] == "mac" else "device-top"


def layout_allowed(layout: str, target: Mapping[str, Any]) -> bool:
    """Whether ``layout`` suits ``target``; ``window-top`` is for Mac only."""
    return layout != "window-top" or target["platform"] == "mac"


def layout_defaults(layout: str, size: tuple[int, int]) -> dict[str, float]:
    """Built-in geometry for ``layout`` at ``size``, with landscape and focus adjustments."""
    defaults = dict(LAYOUT_DEFAULTS)
    if size[0] > size[1]:
        defaults |= LANDSCAPE_LAYOUT
    if layout == "device-focus":
        defaults |= FOCUS_LAYOUT
    return defaults


def typography_defaults(layout: str, size: tuple[int, int]) -> dict[str, dict[str, Any]]:
    """Built-in text settings per field for ``layout`` at ``size``."""
    sizes = {field: values["size"] for field, values in TYPOGRAPHY_DEFAULTS.items()}
    if size[0] > size[1]:
        sizes |= LANDSCAPE_TEXT_SIZES
    if layout == "device-focus":
        sizes |= FOCUS_TEXT_SIZES
    return {
        field: TEXT_DEFAULTS | values | {"size": sizes[field]}
        for field, values in TYPOGRAPHY_DEFAULTS.items()
    }


def resolve_layout(job: Mapping[str, Any]) -> dict[str, float]:
    """The built-in geometry with the job's own layout settings applied."""
    defaults = layout_defaults(job["layout"], (job["width"], job["height"]))
    return defaults | job.get("layoutSettings", {})


def resolve_text(job: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    """Each text field's font (None: default), size, weight, line height, spacing and case."""
    defaults = typography_defaults(job["layout"], (job["width"], job["height"]))
    typography = job.get("typography", {})
    return {field: values | typography.get(field, {}) for field, values in defaults.items()}


def resolve_colors(style: Mapping[str, Any]) -> dict[str, str]:
    """The default palette with the style's colors applied."""
    return STARTER_PALETTES[DEFAULT_PALETTE] | style.get("colors", {})


def studio_appearance() -> dict[str, Any]:
    """Presets and defaults that Studio's controls display."""
    return {
        "starterPalettes": STARTER_PALETTES,
        "defaultPalette": DEFAULT_PALETTE,
        "styleDefaults": STYLE_DEFAULTS,
        "patternDefaults": PATTERN_DEFAULTS,
        "gradientDefaults": GRADIENT_DEFAULTS,
    }
