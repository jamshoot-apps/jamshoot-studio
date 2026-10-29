"""Compose one planned job; previews and exports share these exact pixels."""

from math import ceil, floor
from pathlib import Path
from typing import Any, NamedTuple

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from jamshoot.core.appearance import resolve_colors, resolve_layout, resolve_text
from jamshoot.core.project import ProjectError
from jamshoot.render.background import render_background
from jamshoot.render.devices import DeviceStyle, render_device
from jamshoot.render.images import MAX_IMAGE_PIXELS, load_image
from jamshoot.render.text import Lines, Typography, draw_tracked, fit_text, tracked_length


class TextField(NamedTuple):
    """One text field: key, layout setting for the gap above (or None), line count, palette key."""

    key: str
    gap_setting: str | None
    full_size_lines: int
    palette_key: str


TEXT_STACK = (
    TextField("featureLabel", None, 2, "muted"),
    TextField("headline", "labelGap", 3, "text"),
    TextField("subtitle", "subtitleGap", 3, "muted"),
)
# Long text shrinks to this share of its set size, then fails instead of clipping.
MIN_TEXT_SCALE = 0.6
MIN_SCREENSHOT_HEIGHT = 0.2
MAC_WINDOW_CONTROLS = ("#f27070", "#e6c765", "#72c596")
RENDER_LAYOUTS = {"window-top", "device-top", "device-focus"}
# Where things landed, in canvas pixels, for Studio's guides: each text field's ink box and
# font size, the text and screenshot columns and the framed screenshot.
Guides = dict[str, Any]
Box = list[float]


class PlacedText(NamedTuple):
    """A wrapped text field ready to draw; ``top`` is where its ink starts."""

    field: str
    lines: Lines
    color: str
    top: float
    badge: bool = False


class TextArea(NamedTuple):
    """The canvas size and the width of the text column on it."""

    canvas: tuple[int, int]
    width: int


# A badge eyebrow (``label_style: "badge"``): a pill around a dot and the label, in shares
# of the label's font size (vertical padding from the capitals), and the accent's opacity
# in its fill and outline. The pill and dot are drawn this many times larger, then reduced,
# so their curves are smooth.
BADGE_PAD_X = 1.45
BADGE_PAD_Y = 0.7
BADGE_DOT = 0.55
BADGE_DOT_GAP = 0.55
BADGE_OUTLINE = 0.09
BADGE_FILL_ALPHA = 26
BADGE_OUTLINE_ALPHA = 53
BADGE_SUPERSAMPLE = 4


def _badge_inset(font_size: float) -> float:
    """Horizontal room a badge takes around its label: padding, the dot and its gap."""
    return font_size * (2 * BADGE_PAD_X + BADGE_DOT + BADGE_DOT_GAP)


def _cap_box(draw: ImageDraw.ImageDraw, lines: Lines) -> tuple[float, float]:
    """Top of the first line's capitals and bottom of the last line's, from the origin.

    A badge centers its label on capital height, so descenders don't shift the pill.
    """
    caps = "\n".join("H" for _ in lines.text.split("\n"))
    top, bottom = draw.multiline_textbbox((0, 0), caps, font=lines.font, spacing=lines.spacing)[
        1::2
    ]
    return top, bottom


class Shadow(NamedTuple):
    """A drop shadow: offset below the frame, blur radius and opacity."""

    drop: int
    blur: float
    alpha: int


def _fit_field(
    job: dict[str, Any], line: TextField, style: dict[str, Any], size: tuple[int, int], width: int
) -> Lines:
    """One text field wrapped to ``width``; long text shrinks to no less than ``MIN_TEXT_SCALE``."""
    font_size = max(1, round(size[1] * style["size"] / 100))
    face = job.get("fonts", {}).get(line.key)
    typography = Typography(
        style["weight"],
        style["lineHeight"],
        style["letterSpacing"],
        None if face is None else (face[0], face[1]),
        _badge_inset(1) if line.key == "featureLabel" and job.get("labelStyle") == "badge" else 0,
    )
    box_height = font_size * style["lineHeight"] / 100 * (line.full_size_lines + 0.3)
    font, text = fit_text(
        job[line.key].upper() if style["uppercase"] else job[line.key],
        (width, int(box_height)),
        max_size=font_size,
        min_size=max(1, round(font_size * MIN_TEXT_SCALE)),
        typography=typography,
    )
    return Lines(text, font, typography.spacing(font), typography.tracking(font))


def _layout_text(
    size: tuple[int, int], job: dict[str, Any], settings: dict[str, float]
) -> tuple[list[PlacedText], float]:
    """The text fields stacked from the top margin, and the y where the last one ends."""
    placed: list[PlacedText] = []
    texts = resolve_text(job)
    width = int(size[0] * settings["textWidth"] / 100)
    y = size[1] * settings["topMargin"] / 100
    for line in TEXT_STACK:
        if not job.get(line.key):
            continue
        if placed and line.gap_setting:
            y += size[1] * settings[line.gap_setting] / 100
        item, height = _place_field(job, line, texts[line.key], TextArea(size, width), y)
        placed.append(item)
        y += height
    return placed, y


def _place_field(
    job: dict[str, Any],
    line: TextField,
    style: dict[str, Any],
    area: TextArea,
    y: float,
) -> tuple[PlacedText, float]:
    """The text field placed at ``y`` in ``area``, and its height."""
    size, width = area
    draw = ImageDraw.Draw(Image.new("L", (1, 1)))
    lines = _fit_field(job, line, style, size, width)
    if line.key == "featureLabel" and job.get("labelStyle") == "badge":
        pad = lines.font.size * BADGE_PAD_Y
        top, bottom = _cap_box(draw, lines)
        return PlacedText(line.key, lines, "accent", y + pad - top, True), bottom - top + 2 * pad
    top, bottom = draw.multiline_textbbox(
        (0, 0), lines.text, font=lines.font, spacing=lines.spacing
    )[1::2]
    return PlacedText(line.key, lines, line.palette_key, y - top), bottom - top


def _tracked_box(
    draw: ImageDraw.ImageDraw, lines: Lines, origin: tuple[float, float], center_in: float | None
) -> Box:
    """The area letter-spaced ``lines`` cover: their ink height and widest advance."""
    top, bottom = draw.multiline_textbbox(
        origin, lines.text, font=lines.font, spacing=lines.spacing
    )[1::2]
    widest = max(map(tracked_length(lines.font, lines.tracking), lines.text.split("\n")))
    left = origin[0] if center_in is None else (center_in - widest) / 2
    return [left, top, left + widest, bottom]


class Place(NamedTuple):
    """Where a field is drawn: its first line's top, left edge (None centers it), canvas width."""

    top: float
    left: float | None
    width: int


def _draw_plain(draw: ImageDraw.ImageDraw, lines: Lines, fill: str, place: Place) -> Box:
    """Draw ``lines`` as Pillow sets them and return their ink box."""
    top, left, width = place
    align = "center" if left is None else "left"
    ink_left, _, ink_right, _ = draw.multiline_textbbox(
        (0, 0), lines.text, font=lines.font, spacing=lines.spacing, align=align
    )
    x = (width - (ink_right - ink_left)) / 2 if left is None else left
    position = (x - ink_left, top)
    draw.multiline_text(position, lines.text, fill, lines.font, spacing=lines.spacing, align=align)
    return list(
        draw.multiline_textbbox(
            position, lines.text, font=lines.font, spacing=lines.spacing, align=align
        )
    )


def _draw_spaced(draw: ImageDraw.ImageDraw, lines: Lines, fill: str, place: Place) -> Box:
    """Draw letter-spaced ``lines`` and return the area they cover."""
    top, left, width = place
    center_in = width if left is None else None
    origin = (left or 0, top)
    draw_tracked(draw, origin, lines, fill, center_in)
    return _tracked_box(draw, lines, origin, center_in)


def _draw_text(
    canvas: Image.Image,
    placed: list[PlacedText],
    job: dict[str, Any],
    shift: int,
) -> dict[str, Box]:
    """Draw each field centered, ``shift`` pixels below its planned place; return ink boxes."""
    colors = resolve_colors(job)
    draw = ImageDraw.Draw(canvas)
    boxes: dict[str, Box] = {}
    for item in placed:
        place = Place(item.top + shift, None, canvas.width)
        if item.badge:
            boxes[item.field] = _draw_badge(canvas, item.lines, colors[item.color], place)
            continue
        boxes[item.field] = (_draw_spaced if item.lines.tracking else _draw_plain)(
            draw, item.lines, colors[item.color], place
        )
    return boxes


class BadgeShape(NamedTuple):
    """A badge's ``pill`` and ``dot`` boxes and its label's left edge, ``text_left``."""

    pill: Box
    dot: Box
    text_left: float


def _ink_width(draw: ImageDraw.ImageDraw, lines: Lines) -> float:
    """The widest line as drawn: its ink, or its letter-spaced advance."""
    if lines.tracking:
        return max(map(tracked_length(lines.font, lines.tracking), lines.text.split("\n")))
    left, _, right, _ = draw.multiline_textbbox(
        (0, 0), lines.text, font=lines.font, spacing=lines.spacing
    )
    return right - left


def _badge_shape(draw: ImageDraw.ImageDraw, lines: Lines, place: Place) -> BadgeShape:
    """The badge pill and dot around ``lines`` drawn at ``place``."""
    origin_y, left, width = place
    size = lines.font.size
    pill_width = _ink_width(draw, lines) + _badge_inset(size)
    pill_left = (width - pill_width) / 2 if left is None else left
    cap_top, cap_bottom = _cap_box(draw, lines)
    # The dot sits on the middle of the first line's capitals.
    middle = origin_y + sum(draw.textbbox((0, 0), "H", font=lines.font)[1::2]) / 2
    dot_left, dot = pill_left + size * BADGE_PAD_X, size * BADGE_DOT
    return BadgeShape(
        [
            pill_left,
            origin_y + cap_top - size * BADGE_PAD_Y,
            pill_left + pill_width,
            origin_y + cap_bottom + size * BADGE_PAD_Y,
        ],
        [dot_left, middle - dot / 2, dot_left + dot, middle + dot / 2],
        dot_left + dot + size * BADGE_DOT_GAP,
    )


def _badge_layer(shape: BadgeShape, rgb: tuple[int, int, int], outline: float) -> Image.Image:
    """The pill and dot, smoothed, on a transparent layer covering the pill's pixels."""
    left, top = floor(shape.pill[0]), floor(shape.pill[1])
    size = ceil(shape.pill[2]) - left, ceil(shape.pill[3]) - top

    def scaled(box: Box) -> Box:
        return [
            (value - (left, top)[index % 2]) * BADGE_SUPERSAMPLE for index, value in enumerate(box)
        ]

    large = Image.new("RGBA", (size[0] * BADGE_SUPERSAMPLE, size[1] * BADGE_SUPERSAMPLE))
    pen = ImageDraw.Draw(large)
    pill = scaled(shape.pill)
    pen.rounded_rectangle(
        pill,
        radius=(pill[3] - pill[1]) / 2,
        fill=(*rgb, BADGE_FILL_ALPHA),
        outline=(*rgb, BADGE_OUTLINE_ALPHA),
        width=max(1, round(outline * BADGE_SUPERSAMPLE)),
    )
    pen.ellipse(scaled(shape.dot), fill=(*rgb, 255))
    return large.resize(size, Image.Resampling.LANCZOS)


def _draw_badge(canvas: Image.Image, lines: Lines, accent: str, place: Place) -> Box:
    """Draw ``lines`` in ``accent`` after a dot, in a tinted, outlined pill; return the pill box."""
    shape = _badge_shape(ImageDraw.Draw(canvas), lines, place)
    rgb = int(accent[1:3], 16), int(accent[3:5], 16), int(accent[5:7], 16)
    layer = _badge_layer(shape, rgb, max(1.0, lines.font.size * BADGE_OUTLINE))
    corner = floor(shape.pill[0]), floor(shape.pill[1])
    if canvas.mode == "RGBA":
        canvas.alpha_composite(layer, corner)
    else:
        canvas.paste(layer, corner, layer)
    (_draw_spaced if lines.tracking else _draw_plain)(
        ImageDraw.Draw(canvas), lines, accent, place._replace(left=shape.text_left)
    )
    return shape.pill


def _columns(width: int, settings: dict[str, float], screen: Box) -> list[Box]:
    """The centered text column and the screenshot column."""
    text_width = width * settings["textWidth"] / 100
    left = (width - text_width) / 2
    return [[left, left + text_width], screen]


def _record(
    guides: Guides | None, placed: list[PlacedText], boxes: dict[str, Box], columns: list[Box]
) -> None:
    """Store the text boxes, font sizes and columns in ``guides`` unless it is None."""
    if guides is None:
        return
    guides["copy"] = boxes
    guides["sizes"] = {item.field: item.lines.font.size for item in placed}
    guides["text"], guides["screen"] = columns


def _drop_shadow(
    canvas: Image.Image, mask: Image.Image, origin: tuple[int, int], shadow: Shadow
) -> Image.Image:
    """Composite a blurred copy of ``mask`` below ``origin``; return the canvas as RGBA.

    Only a margin around the mask is blurred. Pillow's Gaussian blur is three box passes of
    at most ``blur + 2`` pixels each, so this margin gives the same pixels as a full blur.
    """
    x, y = origin[0], origin[1] + shadow.drop
    margin = 3 * (ceil(shadow.blur) + 2) + 1
    left, top = max(0, x - margin), max(0, y - margin)
    right = min(canvas.width, x + mask.width + margin)
    bottom = min(canvas.height, y + mask.height + margin)
    layer = Image.new("RGBA", (max(1, right - left), max(1, bottom - top)))
    box = (x - left, y - top, x - left + mask.width, y - top + mask.height)
    layer.paste((0, 0, 0, shadow.alpha), box, mask)
    result = canvas.convert("RGBA")
    result.alpha_composite(layer.filter(ImageFilter.GaussianBlur(shadow.blur)), (left, top))
    return result


def _device(source: Image.Image, job: dict[str, Any], box: tuple[int, int]) -> Image.Image:
    """A framed device that fits ``box``, transparent around its body."""
    style = DeviceStyle(
        job["hardware"], job["deviceFrame"], job["screenshotFit"], job.get("platform")
    )
    return render_device(source, (job["width"], job["height"]), box, style)


def _window(source: Image.Image, job: dict[str, Any], box: tuple[int, int]) -> Image.Image:
    """The screenshot in a rounded Mac app window with a title bar."""
    height = job["height"]
    title_bar = max(16, int(height * 0.038))
    content = ImageOps.contain(
        source, (box[0], max(1, box[1] - title_bar)), method=Image.Resampling.LANCZOS
    )
    window = Image.new(
        "RGBA", (content.width, content.height + title_bar), resolve_colors(job)["frame"]
    )
    window.paste(content, (0, title_bar))
    draw = ImageDraw.Draw(window)
    radius, y = max(2, title_bar // 7), title_bar // 2
    for index, color in enumerate(MAC_WINDOW_CONTROLS):
        x = title_bar // 2 + index * radius * 3
        draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=color)
    mask = Image.new("L", window.size)
    ImageDraw.Draw(mask).rounded_rectangle(
        (0, 0, window.width - 1, window.height - 1), radius=max(8, height // 65), fill=255
    )
    window.putalpha(mask)
    return window


def _compose_stacked(
    canvas: Image.Image, source: Image.Image, job: dict[str, Any], guides: Guides | None
) -> Image.Image:
    """The canvas with the text on top and the screenshot below, centered as a group.

    A nonzero ``screenshotTop`` (% of height) is the screenshot's minimum top, so slides align.
    """
    width, height = canvas.size
    settings = resolve_layout(job)
    placed, text_bottom = _layout_text(canvas.size, job, settings)
    top = max(
        round(text_bottom + height * settings["screenshotGap"] / 100),
        round(height * settings["screenshotTop"] / 100),
    )
    box = (
        int(width * settings["screenshotWidth"] / 100),
        int(height * (1 - settings["bottomMargin"] / 100)) - top,
    )
    if box[1] < height * MIN_SCREENSHOT_HEIGHT:
        raise ProjectError(
            "Layout overflow: text and spacing leave too little room for the screenshot"
        )
    in_window = job["layout"] == "window-top"
    frame = (_window if in_window else _device)(source, job, box)
    shift = (box[1] - frame.height) // 2
    _record(
        guides,
        placed,
        _draw_text(canvas, placed, job, shift),
        _columns(width, settings, [(width - box[0]) / 2, (width + box[0]) / 2]),
    )
    return _place(canvas, frame, ((width - frame.width) // 2, top + shift), in_window, guides)


def _place(
    canvas: Image.Image,
    frame: Image.Image,
    origin: tuple[int, int],
    in_window: bool,
    guides: Guides | None = None,
) -> Image.Image:
    """``frame`` composited at ``origin`` over its drop shadow, as RGB; ``guides`` gets its box."""
    if guides is not None:
        guides["frame"] = [origin[0], origin[1], origin[0] + frame.width, origin[1] + frame.height]
    height = canvas.height
    if in_window:
        shadow = Shadow(9, height / 65, 100)
    else:
        shadow = Shadow(max(4, round(height / 160)), max(2, height / 90), 105)
    canvas = _drop_shadow(canvas, frame.getchannel("A"), origin, shadow)
    canvas.alpha_composite(frame, origin)
    return canvas.convert("RGB")


# A missing screenshot previews as a plain light screen, a quarter of the display size.
PLACEHOLDER = (214, 219, 226)
# Decoded screenshots by path and file version, most recent last, so a preview re-rendered
# on every edit decodes its screenshot once. Rendering only reads them; this many pixels at most.
_SCREENSHOTS: dict[Path, tuple[tuple[int, int], Image.Image]] = {}
CACHED_SCREENSHOT_PIXELS = MAX_IMAGE_PIXELS


def _load_screenshot(path: Path) -> Image.Image:
    """``load_image(path)``, cached by mtime and size, ``CACHED_SCREENSHOT_PIXELS`` at most."""
    stat = path.stat()
    version = (stat.st_mtime_ns, stat.st_size)
    cached = _SCREENSHOTS.pop(path, None)
    image = cached[1] if cached and cached[0] == version else load_image(path)
    _SCREENSHOTS[path] = (version, image)
    while sum(entry.width * entry.height for _, entry in _SCREENSHOTS.values()) > (
        CACHED_SCREENSHOT_PIXELS
    ):
        del _SCREENSHOTS[next(iter(_SCREENSHOTS))]
    return image


def _screenshot(job: dict[str, Any]) -> Image.Image:
    """The job's screenshot, or a light placeholder a quarter of the display size if none."""
    if job["source"] is not None:
        try:
            return _load_screenshot(Path(job["source"]))
        except OSError as error:
            raise ProjectError(f"Cannot decode image {job['source']}: {error}") from error
    width, height = job["width"], job["height"]
    return Image.new("RGB", (max(1, width // 4), max(1, height // 4)), PLACEHOLDER)


def render_job(job: dict[str, Any], guides: Guides | None = None) -> Image.Image:
    """The image for one planned job: background, text, then the screenshot in its layout.

    ``guides``, if given, records where things landed. ProjectError for a bad size or layout.
    """
    width, height = job["width"], job["height"]
    if width < 1 or height < 1 or width * height > MAX_IMAGE_PIXELS:
        raise ProjectError("Output image exceeds pixel limit")
    source = _screenshot(job)
    if job["layout"] == "raw":
        return ImageOps.fit(source, (width, height), method=Image.Resampling.LANCZOS)
    if job["layout"] not in RENDER_LAYOUTS:
        raise ProjectError(f"Unsupported render layout: {job['layout']}")
    if guides is not None:
        guides.update(canvas=[width, height], layout=job["layout"])
    return _compose_stacked(render_background((width, height), job), source, job, guides)
