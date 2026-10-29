"""Font metrics, wrapping and explicit overflow errors; no font fallback."""

import io
import unicodedata
from collections.abc import Callable
from functools import cache
from pathlib import Path
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageFont

from jamshoot.core.project import ProjectError
from jamshoot.fonts import default_face

# Font file contents by path, with the (mtime, size) they were read at.
_FONTS: dict[Path, tuple[tuple[int, int], bytes]] = {}


def _font_bytes(path: Path) -> bytes:
    """The bytes of the font file at ``path``, reread when its mtime or size changes."""
    stat = path.stat()
    version = (stat.st_mtime_ns, stat.st_size)
    cached = _FONTS.get(path)
    if cached is None or cached[0] != version:
        cached = _FONTS[path] = (version, path.read_bytes())
    return cached[1]


# A face as the plan names it: font file and index inside a collection.
FaceRef = tuple[str, int]


def load_font(
    size: int, weight: float | None = None, face: FaceRef | None = None
) -> ImageFont.FreeTypeFont:
    """The font at ``size`` pixels with basic (unshaped) layout.

    ``face`` is (file, index), else the default for ``weight``; only variable fonts use weight.
    """
    file, index = face or default_face(weight)
    path = Path(file)
    try:
        font = ImageFont.truetype(
            io.BytesIO(_font_bytes(path)),
            size=size,
            index=index,
            layout_engine=ImageFont.Layout.BASIC,
        )
    except OSError as error:
        raise ProjectError(f"Cannot load font {path.name}: {error}") from error
    if weight is not None:
        _set_weight(font, weight)
    return font


def _set_weight(font: ImageFont.FreeTypeFont, weight: float) -> None:
    try:
        axes = font.get_variation_axes()
    except OSError:
        return  # Not a variable font.
    values = []
    for axis in axes:
        low, high, default = (float(axis[key] or 0) for key in ("minimum", "maximum", "default"))
        values.append(min(max(weight, low), high) if axis.get("name") == b"Weight" else default)
    font.set_variation_by_axes(values)


def line_spacing(font: ImageFont.FreeTypeFont, line_height: float) -> int:
    """Pillow's extra space between lines for a baseline step of ``line_height`` % of the size."""
    ascent = ImageDraw.Draw(Image.new("L", (1, 1))).textbbox((0, 0), "A", font=font)[3]
    return round(font.size * line_height / 100 - ascent)


def _mask(font: ImageFont.FreeTypeFont, text: str) -> bytes:
    """Rendered coverage of ``text``; equal masks mean identical glyphs."""
    left, top, right, bottom = font.getbbox(text)
    image = Image.new("L", (max(1, int(right - left)), max(1, int(bottom - top))))
    ImageDraw.Draw(image).text((-left, -top), text, font=font, fill=255)
    return image.tobytes()


def _check_characters(text: str, font: ImageFont.FreeTypeFont) -> None:
    missing = _mask(font, "\U0010ffff")
    for char in set(text):
        if char.isspace():
            continue
        category = unicodedata.category(char)
        if (
            unicodedata.bidirectional(char) in {"R", "AL", "AN"}
            or category.startswith("C")
            or _mask(font, char) == missing
        ):
            raise ProjectError(
                f"Unsupported text character U+{ord(char):04X}; font/shaping unavailable"
            )


def _wrap(text: str, measure: Callable[[str], float], width: int) -> str:
    """Greedy word wrap to ``width``, keeping newlines and splitting over-wide words."""
    lines = []
    for paragraph in text.split("\n"):
        line = ""
        for word in paragraph.split():
            candidate = f"{line} {word}".strip()
            if measure(candidate) <= width:
                line = candidate
                continue
            if line:
                lines.append(line)
                line = ""
            for char in word:
                if line and measure(line + char) > width:
                    lines.append(line)
                    line = ""
                line += char
        lines.append(line)
    return "\n".join(lines)


def _balance(text: str, measure: Callable[[str], float], width: int, lines: int) -> str:
    """``text`` rewrapped at the narrowest width that keeps ``lines`` lines, for even lengths."""
    low = 1
    while low < width:
        middle = (low + width) // 2
        if _wrap(text, measure, middle).count("\n") + 1 <= lines:
            width = middle
        else:
            low = middle + 1
    return _wrap(text, measure, width)


class Typography(NamedTuple):
    """Text style: weight, line height, letter spacing, face and horizontal padding.

    Line height and letter spacing are % of font size; ``horizontal_padding`` is in font sizes.
    """

    weight: float | None = None
    line_height: float | None = None
    letter_spacing: float = 0
    face: FaceRef | None = None
    horizontal_padding: float = 0

    def spacing(self, font: ImageFont.FreeTypeFont) -> int:
        """Extra pixels between lines; six without a line height."""
        return 6 if self.line_height is None else line_spacing(font, self.line_height)

    def tracking(self, font: ImageFont.FreeTypeFont) -> float:
        """Pixels added after each character but the last of a line."""
        return font.size * self.letter_spacing / 100


def tracked_length(font: ImageFont.FreeTypeFont, tracking: float) -> Callable[[str], float]:
    """A line's advance width with ``tracking`` between its characters."""
    return lambda line: font.getlength(line) + tracking * max(0, len(line) - 1)


class Lines(NamedTuple):
    """Wrapped ``text`` with its ``font``, extra line ``spacing`` and ``tracking``, in pixels."""

    text: str
    font: ImageFont.FreeTypeFont
    spacing: int
    tracking: float = 0


def draw_tracked(
    draw: ImageDraw.ImageDraw,
    origin: tuple[float, float],
    lines: Lines,
    fill: str,
    center_in: float | None = None,
) -> None:
    """Draw letter-spaced ``lines`` from ``origin``, each centered in ``center_in`` if given."""
    font = lines.font
    measure = tracked_length(font, lines.tracking)
    step = font.getbbox("A")[3] + lines.spacing
    for number, line in enumerate(lines.text.split("\n")):
        x = origin[0] if center_in is None else (center_in - measure(line)) / 2
        y = origin[1] + number * step
        for index, char in enumerate(line):
            advance = font.getlength(line[:index]) + index * lines.tracking
            draw.text((x + advance, y), char, fill, font)


PLAIN = Typography()


def fit_text(
    text: str,
    box: tuple[int, int],
    *,
    max_size: int,
    min_size: int,
    typography: Typography = PLAIN,
) -> tuple[ImageFont.FreeTypeFont, str]:
    """The font and balanced text that fit ``box`` (width, height) at the largest size.

    Sizes run ``max_size`` to ``min_size``. ProjectError for an undrawable character or no fit.
    """
    _check_characters(text, load_font(max_size, face=typography.face))
    draw = ImageDraw.Draw(Image.new("RGB", (1, 1)))
    for size in range(max_size, min_size - 1, -1):
        width = int(box[0] - size * typography.horizontal_padding)
        if width < 1:
            continue
        font = load_font(size, typography.weight, typography.face)
        # Balancing rewraps the same lines at many widths; each prefix is measured once.
        measure = cache(tracked_length(font, typography.tracking(font)))
        wrapped = _wrap(text, measure, width)
        bounds = draw.multiline_textbbox(
            (0, 0), wrapped, font=font, spacing=typography.spacing(font)
        )
        ink_width = (
            max(map(measure, wrapped.split("\n")))
            if typography.letter_spacing
            else bounds[2] - bounds[0]
        )
        if ink_width <= width and bounds[3] - bounds[1] <= box[1]:
            return font, _balance(text, measure, width, wrapped.count("\n") + 1)
    raise ProjectError(f"Text overflow: text does not fit {box[0]}x{box[1]} at {min_size}px")
