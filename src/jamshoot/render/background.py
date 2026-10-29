"""Seeded backgrounds; no global RNG or per-pixel Python loops."""

import math
import random
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from functools import cached_property
from typing import Any

from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageOps

from jamshoot.core.appearance import GRADIENT_DEFAULTS, PATTERN_DEFAULTS, resolve_colors
from jamshoot.core.project import ProjectError


def _density(settings: Mapping[str, float]) -> float:
    # Sub-percent densities share the sparsest geometry; zero disables the layer.
    return max(1, settings["density"]) / 50


@dataclass(frozen=True)
class Brush:
    """One pattern's seeded geometry, painted as an alpha mask on a square field."""

    canvas: tuple[int, int]
    cell: int
    step: int
    stroke: int
    phase: tuple[float, float, float]
    rng: random.Random
    settings: Mapping[str, float]

    @cached_property
    def field(self) -> int:
        """The field's side: the canvas diagonal, rounded up, plus 6 pixels for sampling."""
        return math.ceil(math.hypot(*self.canvas)) + 6

    @cached_property
    def origin(self) -> tuple[int, int]:
        """The canvas's top-left corner in field coordinates."""
        return (self.field - self.canvas[0]) // 2, (self.field - self.canvas[1]) // 2

    @cached_property
    def mask(self) -> Image.Image:
        """The pattern's coverage; the accent color is applied after rotation."""
        return Image.new("L", (self.field, self.field))

    @cached_property
    def draw(self) -> ImageDraw.ImageDraw:
        """A drawing context on the mask."""
        return ImageDraw.Draw(self.mask)

    @property
    def alpha(self) -> int:
        """Mask value of a painted pixel: the pattern opacity."""
        return round(self.settings["opacity"] * 255 / 100)

    @property
    def unit(self) -> int:
        """The canvas's short side in pixels."""
        return min(self.canvas)

    @cached_property
    def offsets(self) -> tuple[int, int]:
        """Seeded x and y lattice shifts, each 0 to ``step`` pixels."""
        return round(self.phase[0] * self.step), round(self.phase[1] * self.step)

    @property
    def rotation(self) -> float:
        """The rotation setting in degrees plus a seeded tilt of up to 15 degrees either way."""
        return self.settings["rotation"] + (self.phase[2] - 0.5) * 30

    def ticks(self, axis: int, start: int = 0, spacing: int | None = None) -> range:
        """Positions on one field axis, ``spacing`` (default ``step``) apart, from ``start``."""
        spacing = spacing or self.step
        return range((self.origin[axis] + start) % spacing - spacing, self.field + spacing, spacing)

    def lattice(self, turn: bool = False) -> Iterator[tuple[float, float]]:
        """Grid points every ``step`` pixels from the seeded offsets.

        ``turn`` rotates the points about the canvas center, which keeps small dots sharp.
        """
        theta = math.radians(self.rotation) if turn else 0
        cosine, sine = math.cos(theta), math.sin(theta)
        cx, cy = self.origin[0] + self.canvas[0] / 2, self.origin[1] + self.canvas[1] / 2
        for x in self.ticks(0, self.offsets[0]):
            for y in self.ticks(1, self.offsets[1]):
                dx, dy = x - cx, y - cy
                yield cx + cosine * dx + sine * dy, cy - sine * dx + cosine * dy

    def count(self, per_canvas: float) -> int:
        """The field's shape count for ``per_canvas`` per canvas at this density; at least 1."""
        area = self.field**2 / (self.canvas[0] * self.canvas[1])
        return max(1, round(per_canvas * _density(self.settings) * area))

    def scatter(self) -> tuple[int, int]:
        """A seeded point on the field."""
        return self.rng.randrange(self.field), self.rng.randrange(self.field)


def _dots(brush: Brush) -> None:
    radius = brush.cell // 14
    for x, y in brush.lattice(turn=True):
        if radius:
            brush.draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=brush.alpha)
        else:
            brush.draw.point((x, y), fill=brush.alpha)


def _circles(brush: Brush) -> None:
    radius = brush.cell // 3
    for x, y in brush.lattice(turn=True):
        if radius:
            box = (x - radius, y - radius, x + radius, y + radius)
            brush.draw.ellipse(box, outline=brush.alpha, width=brush.stroke)
        else:
            brush.draw.point((x, y), fill=brush.alpha)


def _grid(brush: Brush) -> None:
    field = brush.field
    for x in brush.ticks(0, brush.offsets[0]):
        brush.draw.line((x, 0, x, field), fill=brush.alpha, width=brush.stroke)
    for y in brush.ticks(1, brush.offsets[1]):
        brush.draw.line((0, y, field, y), fill=brush.alpha, width=brush.stroke)


def _hatch(brush: Brush, *, crossed: bool) -> None:
    field, step = brush.field, brush.step
    left, top = brush.origin
    dx, dy = brush.offsets
    falling = (left - top + dx - dy) % step - step * (field // step + 2)
    for x in range(falling, field + step, step):
        brush.draw.line((x, 0, x + field, field), fill=brush.alpha, width=brush.stroke)
    if crossed:
        rising = (left + top + dx + dy) % step
        for x in range(rising, 2 * field + step, step):
            brush.draw.line((x, 0, x - field, field), fill=brush.alpha, width=brush.stroke)


def _waves(brush: Brush) -> None:
    left = brush.origin[0]
    period = max(1, brush.unit * brush.settings["scale"] / 100)
    height = brush.cell * brush.settings["amplitude"] / 100
    sampling = max(1, min(4, math.floor(period / 16)))
    for y in brush.ticks(1, brush.offsets[1]):
        points = [
            (x, y + math.sin(((x - left) / period + brush.phase[0]) * math.tau) * height)
            for x in brush.ticks(0, spacing=sampling)
        ]
        brush.draw.line(points, fill=brush.alpha, width=brush.stroke * 2)


# Mesh columns against its rows: amplitude, stroke and opacity shares, and how far each
# column may stray from its lattice place, in steps.
MESH_COLUMN = (0.86, 0.82, 0.58)
MESH_JITTER = 0.18


def _mesh(brush: Brush) -> None:
    """Draw horizontal waves crossed by fainter, thinner vertical waves with seeded jitter."""
    amplitude, stroke, opacity = MESH_COLUMN
    top = brush.origin[1]
    period = max(1, brush.unit * brush.settings["scale"] / 100)
    height = brush.cell * brush.settings["amplitude"] / 100 * amplitude
    width = max(1, round(brush.stroke * 2 * stroke))
    sampling = max(1, min(4, math.floor(period / 16)))
    for x in brush.ticks(0, brush.offsets[0]):
        column = x + brush.rng.random() * brush.step * MESH_JITTER
        points = [
            (column + math.sin(((y - top) / period + brush.phase[1]) * math.tau) * height, y)
            for y in brush.ticks(1, spacing=sampling)
        ]
        brush.draw.line(points, fill=round(brush.alpha * opacity), width=width)
    # Draw the brighter rows last: intersections keep the maximum coverage.
    _waves(brush)


def _arcs(brush: Brush) -> None:
    left, top = brush.origin
    x, y = left + brush.offsets[0], top + brush.offsets[1]
    # The seeded center may lie outside the field when spacing exceeds its size.
    # Include every ring whose inward stroke could still reach a field corner.
    limit = math.ceil(
        max(math.hypot(x - cx, y - cy) for cx in (0, brush.field) for cy in (0, brush.field))
    )
    for radius in range(brush.step, limit + brush.stroke * 2 + 1, brush.step):
        box = (x - radius, y - radius, x + radius, y + radius)
        brush.draw.arc(box, 0, 360, fill=brush.alpha, width=brush.stroke * 2)


def _confetti(brush: Brush) -> None:
    cell = brush.cell
    for _ in range(brush.count(130)):
        x, y = brush.scatter()
        end = (x + brush.rng.randrange(-cell // 3, cell // 3 + 1), y + cell // 5)
        brush.draw.line((x, y, *end), fill=brush.alpha, width=max(2, brush.stroke * 2))


def _chevrons(brush: Brush) -> None:
    left, cell = brush.origin[0] + brush.offsets[0], brush.cell
    for y in brush.ticks(1, brush.offsets[1]):
        points = [
            (x, y + (0 if (x - left) // cell % 2 else cell // 2))
            for x in brush.ticks(0, brush.offsets[0], spacing=cell)
        ]
        brush.draw.line(points, fill=brush.alpha, width=brush.stroke * 2)


def _tiles(brush: Brush) -> Iterator[tuple[int, int, int, int]]:
    """Row, column and top-left corner of each cell, offset by the seeded phase."""
    left, top = brush.origin
    dx, dy = brush.offsets
    for y in brush.ticks(1, dy):
        for x in brush.ticks(0, dx):
            yield (y - top - dy) // brush.step, (x - left - dx) // brush.step, x, y


def _checkerboard(brush: Brush) -> None:
    for row, column, x, y in _tiles(brush):
        if (row + column) % 2:
            box = (x, y, x + brush.step - 1, y + brush.step - 1)
            brush.draw.rectangle(box, fill=brush.alpha)


def _polygons(brush: Brush, *, sides: int, inner: float) -> None:
    """Draw an outlined ``sides``-gon per tile, or a filled star when ``inner`` is below 1."""
    radius = brush.cell * 0.45
    for _, _, x, y in _tiles(brush):
        points = [
            (
                x + math.cos(i * math.tau / sides) * radius * (inner if i % 2 else 1),
                y + math.sin(i * math.tau / sides) * radius * (inner if i % 2 else 1),
            )
            for i in range(sides)
        ]
        if inner < 1:
            brush.draw.polygon(points, fill=brush.alpha)
        else:
            brush.draw.line(points + [points[0]], fill=brush.alpha, width=brush.stroke)


PAINTERS: dict[str, Callable[[Brush], None]] = {
    "dots": _dots,
    "circles": _circles,
    "grid": _grid,
    "diagonal": lambda brush: _hatch(brush, crossed=False),
    "crosshatch": lambda brush: _hatch(brush, crossed=True),
    "mesh": _mesh,
    "waves": _waves,
    "arcs": _arcs,
    "confetti": _confetti,
    "chevrons": _chevrons,
    "hexagons": lambda brush: _polygons(brush, sides=6, inner=1),
    "stars": lambda brush: _polygons(brush, sides=10, inner=0.4),
    "checkerboard": _checkerboard,
}
# Patterns of round shapes on the lattice, turned point by point.
ROUND_LATTICES = {"dots", "circles"}


def _window(mask: Image.Image, brush: Brush, rotation: float) -> Image.Image:
    """The canvas part of the field, turned ``rotation`` degrees counter-clockwise."""
    (width, height), (left, top) = brush.canvas, brush.origin
    if not rotation:
        return mask.crop((left, top, left + width, top + height))
    cosine, sine = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
    x, y = left + width / 2, top + height / 2
    half_width, half_height = width / 2, height / 2
    inverse = (
        cosine,
        -sine,
        x - cosine * half_width + sine * half_height,
        sine,
        cosine,
        y - sine * half_width - cosine * half_height,
    )
    turned = mask.transform(brush.canvas, Image.Transform.AFFINE, inverse, Image.Resampling.BICUBIC)
    # Bicubic ringing must not make edges more opaque than the painted shapes.
    return turned.point([min(value, brush.alpha) for value in range(256)])


# Pillow's radial gradient reaches this value on the circle inscribed in its 256 px square.
RADIAL_EDGE = 181


def _radial(size: tuple[int, int], gradient: Mapping[str, Any]) -> Image.Image:
    """Radial gray levels from the center; RADIAL_EDGE at ``radius`` % of the farthest corner."""
    width, height = size
    cx, cy = width * gradient["centerX"] / 100, height * gradient["centerY"] / 100
    corner = max(math.hypot(x - cx, y - cy) for x in (0, width) for y in (0, height))
    scale = 128 / max(1.0, corner * gradient["radius"] / 100)
    matrix = (scale, 0.0, 128 - cx * scale, 0.0, scale, 128 - cy * scale)
    return Image.radial_gradient("L").transform(
        size, Image.Transform.AFFINE, matrix, Image.Resampling.BILINEAR, fillcolor=RADIAL_EDGE
    )


def _linear(size: tuple[int, int], angle: float) -> Image.Image:
    """Gray levels 0–255 along the CSS gradient ``angle``, ends at opposite corners."""
    width, height = size
    theta = math.radians(angle)
    dx, dy = math.sin(theta), -math.cos(theta)
    step = 255 / (abs(width * dx) + abs(height * dy))
    offset = 127.5 - step * (dx * width + dy * height) / 2
    matrix = (0.0, 0.0, 128.0, dx * step, dy * step, offset)
    return Image.linear_gradient("L").transform(
        size, Image.Transform.AFFINE, matrix, Image.Resampling.BILINEAR
    )


def _ramp(size: tuple[int, int], gradient: Mapping[str, Any]) -> Image.Image:
    """Gray levels 0–255 along the gradient, bent by the midpoint unless ``stops`` is set."""
    midpoint = 50 if "stops" in gradient else gradient["midpoint"]
    exponent = math.log(0.5) / math.log(midpoint / 100)
    if gradient["kind"] == "radial":
        ramp, edge = _radial(size, gradient), RADIAL_EDGE
    elif gradient["angle"] % 360 == 180 and exponent == 1:
        return Image.linear_gradient("L").resize(size)
    else:
        ramp, edge = _linear(size, gradient["angle"]), 255
    levels = [round(255 * min(1.0, value / edge) ** exponent) for value in range(256)]
    return ramp.point(levels)


def _stop_levels(stops: list[Mapping[str, Any]]) -> list[int]:
    """The 768-value lookup table (256 each for R, G, B) that colors a ramp through ``stops``."""
    ordered = sorted(stops, key=lambda stop: stop["position"])
    points = [(stop["position"], ImageColor.getrgb(stop["color"])[:3]) for stop in ordered]
    channels: list[list[int]] = [[], [], []]
    color: tuple[int, ...]
    for value in range(256):
        position = value * 100 / 255
        after = next((index for index, point in enumerate(points) if point[0] >= position), None)
        if after is None:
            color = points[-1][1]
        elif after == 0:
            color = points[0][1]
        else:
            (start, low), (end, high) = points[after - 1], points[after]
            share = (position - start) / (end - start) if end > start else 1
            color = tuple(round(a + (b - a) * share) for a, b in zip(low, high, strict=True))
        for channel, level in zip(channels, color, strict=True):
            channel.append(level)
    return [level for channel in channels for level in channel]


def _fill(
    size: tuple[int, int], style: Mapping[str, Any], colors: Mapping[str, str]
) -> Image.Image:
    """The background under the pattern: one color, or a gradient through its colors."""
    gradient = GRADIENT_DEFAULTS | style.get("gradient", {})
    if gradient["kind"] == "solid":
        return Image.new("RGBA", size, colors["top"])
    ramp = _ramp(size, gradient)
    if "stops" in gradient:
        return ramp.convert("RGB").point(_stop_levels(gradient["stops"])).convert("RGBA")
    return ImageOps.colorize(ramp, colors["top"], colors["bottom"]).convert("RGBA")


def _glows(base: Image.Image, glows: list[Mapping[str, Any]]) -> None:
    """Blend each glow, a blurred disc of its color, into ``base``.

    Only the disc's neighborhood is painted, so a glow centered off the canvas still lights it.
    """
    width, height = base.size
    unit = min(base.size)
    for glow in glows:
        radius, blur = unit * glow["radius"] / 100, unit * glow["blur"] / 100
        margin = math.ceil(radius + 3 * blur) + 2
        left = math.floor(width * glow["x"] / 100) - margin
        top = math.floor(height * glow["y"] / 100) - margin
        center_x, center_y = width * glow["x"] / 100 - left, height * glow["y"] / 100 - top
        mask = Image.new("L", (2 * margin, 2 * margin))
        ImageDraw.Draw(mask).ellipse(
            (center_x - radius, center_y - radius, center_x + radius, center_y + radius),
            fill=round(glow["opacity"] * 255 / 100),
        )
        if blur:
            mask = mask.filter(ImageFilter.GaussianBlur(blur))
        light = Image.new("RGBA", mask.size, ImageColor.getrgb(glow["color"])[:3])
        base.paste(light, (left, top), mask)


def render_background(size: tuple[int, int], style: Mapping[str, Any]) -> Image.Image:
    """The RGB background of ``size`` for ``style``: fill, glows, then the seeded pattern."""
    colors = resolve_colors(style)
    settings = PATTERN_DEFAULTS | style.get("patternSettings", {})
    base = _fill(size, style, colors)
    _glows(base, style.get("glows", []))
    pattern = style["pattern"]
    if pattern == "none" or settings["density"] == 0 or settings["opacity"] == 0:
        return base.convert("RGB")
    if pattern not in PAINTERS:
        raise ProjectError(f"Unsupported pattern: {pattern}")
    placement = random.Random(f"{style['seed']}:placement")
    unit, scale = min(size), settings["scale"] / 100
    cell = max(1, round(unit / 9 * scale))
    # ponytail: cap lattice axes at 1000 intervals even on very narrow custom canvases.
    step = max(2, math.ceil(math.hypot(*size) / 1000), round(cell / _density(settings)))
    brush = Brush(
        canvas=size,
        cell=cell,
        step=step,
        stroke=max(1, round(max(1, unit // 180) * settings["strokeWidth"])),
        phase=(
            placement.random(),
            placement.random(),
            placement.random() if pattern != "confetti" else 0.5,
        ),
        rng=random.Random(style["seed"]),
        settings=settings,
    )
    PAINTERS[pattern](brush)
    mask = brush.mask
    layer = Image.new("RGBA", size, ImageColor.getrgb(colors["accent"])[:3])
    rotation = 0 if pattern in ROUND_LATTICES else brush.rotation
    layer.putalpha(_window(mask, brush, rotation))
    return Image.alpha_composite(base, layer).convert("RGB")
