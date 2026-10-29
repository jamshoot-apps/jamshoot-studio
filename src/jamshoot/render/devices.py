"""Procedural device frames; sources of the proportions are in docs/rendering.md.

Geometry is in units of the screen's short side, so one description fits every size.
Boxes are ``(left, top, right, bottom)`` with exclusive right and bottom edges.
"""

from collections.abc import Callable
from dataclasses import dataclass
from functools import partial
from math import ceil, floor, pi, sin
from typing import NamedTuple

from PIL import Image, ImageDraw, ImageOps

SUPERSAMPLE = 2
Box = tuple[float, float, float, float]
Color = tuple[int, int, int]
Corners = tuple[bool, bool, bool, bool]
TOP_CORNERS: Corners = (True, True, False, False)
BOTTOM_CORNERS: Corners = (False, False, True, True)


class Shape(NamedTuple):
    """An anti-aliased primitive: ``rect``, ``rrect`` or ``ellipse``; ``clear`` erases."""

    kind: str
    box: Box
    radius: float = 0
    corners: Corners | None = None
    clear: bool = False


@dataclass(frozen=True)
class Bezels:
    """Front bezel widths around the screen, in screen short-side units."""

    side: float
    top: float
    bottom: float


@dataclass(frozen=True)
class Spec:
    """Proportions of one phone or tablet family, in screen short-side units."""

    bezels: Bezels
    screen_radius: float
    body_radius: float
    band: float  # visible metal band around the front glass
    cutout: str  # island, notch, home, camera, tablet-home, punch-hole or none
    buttons: str  # phone, phone-home, tablet, duo-closed, duo-open or none
    spine: bool = False  # square leading corners: the hinge side of a closed foldable


@dataclass(frozen=True)
class DeviceStyle:
    """How a screenshot is framed: hardware family, frame finish, fit and target platform."""

    hardware: str
    frame: str
    fit: str
    platform: str | None = None


SPECS = {
    "island": Spec(Bezels(0.043, 0.043, 0.043), 0.145, 0.19, 0.011, "island", "phone"),
    "notch": Spec(Bezels(0.048, 0.048, 0.048), 0.115, 0.165, 0.012, "notch", "phone"),
    "home": Spec(Bezels(0.073, 0.29, 0.29), 0.0, 0.17, 0.008, "home", "phone-home"),
    "tablet": Spec(Bezels(0.05, 0.05, 0.05), 0.022, 0.072, 0.008, "camera", "tablet"),
    "tablet-home": Spec(Bezels(0.07, 0.14, 0.14), 0.0, 0.085, 0.006, "tablet-home", "tablet"),
    "plain": Spec(Bezels(0.045, 0.045, 0.045), 0.06, 0.1, 0.01, "none", "phone"),
    "duo-outer": Spec(
        Bezels(0.045, 0.036, 0.036), 0.075, 0.12, 0.022, "punch-hole", "duo-closed", spine=True
    ),
    "duo-inner": Spec(Bezels(0.031, 0.031, 0.031), 0.082, 0.113, 0.012, "none", "duo-open"),
}
NO_BEZELS = Bezels(0, 0, 0)
HOME_BUTTON_CUTOUTS = {"home", "tablet-home"}
# Rounded corners as (top left, top right, bottom right, bottom left), portrait.
SPINE_CORNERS: Corners = (False, True, True, False)
# Side buttons as (start, length) fractions of the body height: (left side, right side).
BUTTONS = {
    "phone": (((0.17, 0.035), (0.25, 0.065), (0.335, 0.065)), ((0.28, 0.1),)),
    "phone-home": (((0.13, 0.03), (0.21, 0.055), (0.29, 0.055)), ((0.21, 0.07),)),
    "tablet": ((), ((0.07, 0.05), (0.135, 0.05))),
    "duo-closed": ((), ((0.28, 0.16),)),
    "duo-open": (((0.127, 0.07), (0.2, 0.074)), ()),
}
# Buttons on the top edge as (start, length) fractions of the body width.
TOP_BUTTONS = {
    "tablet": ((0.76, 0.12),),
    "duo-closed": ((0.45, 0.14), (0.61, 0.14)),
    "duo-open": ((0.283, 0.161),),
}

# MacBook Pro 14": 3024x1964 display, ≈5 mm side bezels and a camera housing.
LAPTOP_DISPLAY = 3024 / 1964
LID = Bezels(0.018, 0.03, 0.042)
DECK_OVERHANG = 0.075  # on each side, as a fraction of the lid width
DECK_HEIGHT = 0.042

PALETTES = {
    "black": {
        "band": (58, 59, 63),
        "edge": (28, 29, 32),
        "button": (48, 49, 53),
        "bezel": (9, 10, 12),
        "front": (9, 10, 12),
        "deck": (52, 54, 59),
        "deck_shade": (34, 35, 39),
    },
    "silver": {
        "band": (220, 222, 226),
        "edge": (158, 163, 170),
        "button": (196, 199, 204),
        "bezel": (9, 10, 12),
        "front": (246, 246, 248),
        "deck": (214, 217, 222),
        "deck_shade": (170, 175, 182),
    },
}
# Visual metal approximations from Apple's product images, not official RGB values.
DUO_FINISHES = {
    "black": {
        "band": (51, 62, 76),
        "edge": (23, 29, 38),
        "button": (41, 50, 63),
    },
    "silver": {
        "band": (220, 219, 215),
        "edge": (161, 161, 156),
        "button": (198, 197, 192),
    },
}
# Camera glass and the Dynamic Island are near-black on every finish.
GLASS = {"island": (5, 5, 7), "lens": (17, 18, 22), "tablet": (30, 32, 38), "laptop": (34, 36, 44)}


def _device_palette(style: DeviceStyle) -> dict[str, Color]:
    palette = PALETTES.get(style.frame, PALETTES["black"])
    if style.hardware in {"duo-outer", "duo-inner"}:
        return {**palette, **DUO_FINISHES.get(style.frame, {})}
    return palette


@dataclass(frozen=True)
class _Layout:
    """Pixel geometry of one device inside its transparent canvas."""

    unit: int  # screen short side
    size: tuple[int, int]  # canvas, including protruding buttons or the laptop deck
    body: Box  # phone body or laptop lid
    screen: tuple[int, int]
    origin: tuple[int, int]  # screen top-left in the canvas

    @property
    def screen_box(self) -> Box:
        """The screen's box in canvas coordinates."""
        x, y = self.origin
        return (x, y, x + self.screen[0], y + self.screen[1])


def _inset(box: Box, amount: float) -> Box:
    return (box[0] + amount, box[1] + amount, box[2] - amount, box[3] - amount)


def _circle(center: tuple[float, float], radius: float) -> Box:
    return (center[0] - radius, center[1] - radius, center[0] + radius, center[1] + radius)


def _mask(
    size: tuple[int, int], shapes: list[Shape], offset: tuple[int, int] = (0, 0)
) -> Image.Image:
    """Supersampled coverage of ``shapes`` drawn relative to ``offset``."""
    mask = Image.new("L", (size[0] * SUPERSAMPLE, size[1] * SUPERSAMPLE))
    draw = ImageDraw.Draw(mask)
    for shape in shapes:
        left, top, right, bottom = shape.box
        box = (
            round((left - offset[0]) * SUPERSAMPLE),
            round((top - offset[1]) * SUPERSAMPLE),
            round((right - offset[0]) * SUPERSAMPLE) - 1,
            round((bottom - offset[1]) * SUPERSAMPLE) - 1,
        )
        fill = 0 if shape.clear else 255
        if shape.kind == "rrect":
            radius = max(0, shape.radius * SUPERSAMPLE)
            draw.rounded_rectangle(box, radius=radius, fill=fill, corners=shape.corners)
        elif shape.kind == "ellipse":
            draw.ellipse(box, fill=fill)
        else:
            draw.rectangle(box, fill=fill)
    return mask.reduce(SUPERSAMPLE)


def _fill(canvas: Image.Image, color: Color, *shapes: Shape) -> None:
    """Composite one solid color through the anti-aliased union of ``shapes``."""
    boxes = [shape.box for shape in shapes if not shape.clear]
    left = max(0, floor(min(box[0] for box in boxes)))
    top = max(0, floor(min(box[1] for box in boxes)))
    right = min(canvas.width, ceil(max(box[2] for box in boxes)))
    bottom = min(canvas.height, ceil(max(box[3] for box in boxes)))
    layer = Image.new("RGBA", (max(1, right - left), max(1, bottom - top)), (*color, 255))
    layer.putalpha(_mask(layer.size, list(shapes), (left, top)))
    canvas.alpha_composite(layer, (left, top))


def _paste(
    canvas: Image.Image, content: Image.Image, origin: tuple[int, int], shapes: list[Shape]
) -> None:
    """Composite ``content`` at ``origin`` through screen-local ``shapes``."""
    layer = content.convert("RGBA")
    layer.putalpha(_mask(layer.size, shapes))
    canvas.alpha_composite(layer, origin)


def _content(screenshot: Image.Image, screen: tuple[int, int], fit: str) -> Image.Image:
    if fit == "cover":
        return ImageOps.fit(screenshot, screen, method=Image.Resampling.LANCZOS)
    # The screen already matches the screenshot's aspect; padding only absorbs rounding.
    return ImageOps.pad(screenshot, screen, method=Image.Resampling.LANCZOS, color="white")


def _largest(layout: Callable[[int], _Layout], unit: int, box: tuple[int, int]) -> _Layout:
    """Shrink from ``unit`` until integer-rounded bezels keep the device inside ``box``."""
    result = layout(unit)
    while unit > 1 and (result.size[0] > box[0] or result.size[1] > box[1]):
        unit -= 1
        result = layout(unit)
    return result


class Protrusion(NamedTuple):
    """How far buttons stick out of the body, in screen short-side units."""

    side: float
    top: float


def _phone_layout(
    unit: int, aspect: float, bezels: Bezels, buttons: Protrusion, spine: float = 0
) -> _Layout:
    """Pixel layout of a phone with a ``unit``-wide screen."""
    screen = (unit, max(1, round(unit * aspect)))
    dx, dy = round(buttons.side * unit), round(buttons.top * unit)
    hinge = round(spine * unit)
    width = screen[0] + 2 * round(bezels.side * unit)
    height = screen[1] + round(bezels.top * unit) + round(bezels.bottom * unit)
    origin = (dx + hinge + round(bezels.side * unit), dy + round(bezels.top * unit))
    return _Layout(
        unit,
        (width + 2 * dx + hinge, height + dy),
        (dx + hinge, dy, dx + hinge + width, dy + height),
        screen,
        origin,
    )


def _laptop_layout(unit: int, aspect: float) -> _Layout:
    screen = (unit, max(1, round(unit / aspect)))
    lid_w = screen[0] + 2 * round(LID.side * unit)
    lid_h = screen[1] + round(LID.top * unit) + round(LID.bottom * unit)
    width = round(lid_w * (1 + 2 * DECK_OVERHANG))
    left = (width - lid_w) / 2
    size = (width, lid_h + max(2, round(DECK_HEIGHT * unit)))
    origin = (round(left + LID.side * unit), round(LID.top * unit))
    return _Layout(unit, size, (left, 0, left + lid_w, lid_h), screen, origin)


class _Phone:
    """Draws a portrait phone or tablet; the caller rotates landscape screenshots."""

    def __init__(self, layout: _Layout, spec: Spec, palette: dict[str, Color], landscape: bool):
        self.layout, self.spec, self.palette = layout, spec, palette
        self.landscape = landscape
        self.image = Image.new("RGBA", layout.size)

    @property
    def front(self) -> Color:
        """Front glass color: the finish on Home button devices, else black."""
        return self.palette["front" if self.spec.cutout in HOME_BUTTON_CUTOUTS else "bezel"]

    def _units(self, value: float) -> float:
        return value * self.layout.unit

    def shell(self) -> None:
        """Draw the buttons, the metal edge and band, then the front glass."""
        spec, body = self.spec, self.layout.body
        if spec.screen_radius:
            radius = self._units(spec.screen_radius + spec.bezels.side)
        else:
            radius = self._units(spec.body_radius)
        edge = max(1.0, self._units(0.0025))
        glass = max(1.0, self._units(spec.band)) + edge
        corners = SPINE_CORNERS if spec.spine else None
        buttons = self._buttons()
        if buttons:
            _fill(self.image, self.palette["button"], *buttons)
        if spec.spine:
            self._hinge()
        _fill(self.image, self.palette["edge"], Shape("rrect", body, radius, corners))
        band = Shape("rrect", _inset(body, edge), radius - edge, corners)
        _fill(self.image, self.palette["band"], band)
        if spec.spine:
            # The front half meets the rounded hinge barrel at a narrow seam.
            x = body[0] + (edge + glass) / 2
            seam = (x, body[1] + edge, x + edge, body[3] - edge)
            _fill(self.image, self.palette["edge"], Shape("rect", seam))
        _fill(self.image, self.front, Shape("rrect", _inset(body, glass), radius - glass, corners))
        if spec.cutout in HOME_BUTTON_CUTOUTS:
            # Home button devices show a black display border inside the colored front.
            border = max(1, round(self._units(0.006)))
            screen = _inset(self.layout.screen_box, -border)
            _fill(self.image, self.palette["bezel"], Shape("rect", screen))

    def _hinge(self) -> None:
        """Draw a narrow rounded hinge barrel behind the closed device's straight glass edge."""
        left, top, _, bottom = self.layout.body
        width = max(2, round(self._units(0.032)))
        inset = max(1, round(self._units(0.012)))
        height = max(1, round(bottom - top) - 2 * inset)
        layer = Image.new("RGBA", (width, height))
        draw = ImageDraw.Draw(layer)
        for x in range(width):
            light = sin(pi * x / max(1, width - 1)) * 0.7
            color = tuple(
                round(shade + (highlight - shade) * light)
                for shade, highlight in zip(self.palette["edge"], self.palette["band"], strict=True)
            )
            draw.line((x, 0, x, height), fill=(*color, 255))
        layer.putalpha(
            _mask(
                layer.size,
                [Shape("rrect", (0, 0, width, height), width / 2, (True, False, False, True))],
            )
        )
        self.image.alpha_composite(layer, (round(left - self._units(0.028)), round(top) + inset))

    def _buttons(self) -> list[Shape]:
        """The side and, on some devices, top-edge button shapes."""
        width, height = self.layout.size
        depth = round(self._units(0.009)) + self._units(0.004)
        left, right = BUTTONS.get(self.spec.buttons, ((), ()))
        shapes = [
            Shape("rrect", (x, start * height, x + depth, (start + length) * height), depth / 2)
            for x, spans in ((0, left), (width - depth, right))
            for start, length in spans
        ]
        shapes += [
            Shape("rrect", (start * width, 0, (start + length) * width, depth), depth / 2)
            for start, length in TOP_BUTTONS.get(self.spec.buttons, ())
        ]
        return shapes

    def screen(self, content: Image.Image, radius: float) -> None:
        """Paste the screenshot with rounded corners and any notch cut out."""
        corners = SPINE_CORNERS if self.spec.spine else None
        shapes = [Shape("rrect", (0, 0, *self.layout.screen), radius, corners)]
        if self.spec.cutout == "notch":
            shapes += self._notch()
        _paste(self.image, content, self.layout.origin, shapes)

    def _notch(self) -> list[Shape]:
        """The iPhone X to 14 notch with concave shoulders, in screen coordinates."""
        notch_w, notch_h = self._units(0.45), self._units(0.083)
        radius, ear = self._units(0.036), self._units(0.018)
        left = (self.layout.screen[0] - notch_w) / 2
        right = left + notch_w
        return [
            Shape("rrect", (left, -radius, right, notch_h), radius, clear=True),
            Shape("rect", (left - ear, 0, left, ear), clear=True),
            Shape("ellipse", (left - 2 * ear, 0, left, 2 * ear)),
            Shape("rect", (right, 0, right + ear, ear), clear=True),
            Shape("ellipse", (right, 0, right + 2 * ear, 2 * ear)),
        ]

    def cutout(self) -> None:
        """Draw the family's Dynamic Island, Home button, camera or punch-hole, if it has one."""
        draw = {
            "island": self._island,
            "home": self._phone_home,
            "camera": self._camera,
            "tablet-home": self._tablet_home,
            "punch-hole": self._punch_hole,
        }.get(self.spec.cutout)
        if draw is not None:
            draw()

    @property
    def _forehead(self) -> tuple[float, float]:
        """The center of the bezel above the screen."""
        left, top, right, _ = self.layout.screen_box
        return (left + right) / 2, top - self._units(self.spec.bezels.top) / 2

    @property
    def _chin(self) -> tuple[float, float]:
        """The center of the bezel below the screen."""
        left, _, right, bottom = self.layout.screen_box
        return (left + right) / 2, bottom + self._units(self.spec.bezels.bottom) / 2

    def _island(self) -> None:
        center, top = self._forehead[0], self.layout.origin[1] + self._units(0.03)
        width, height = self._units(0.32), self._units(0.094)
        pill = (center - width / 2, top, center + width / 2, top + height)
        _fill(self.image, GLASS["island"], Shape("rrect", pill, height / 2))

    def _phone_home(self) -> None:
        self._home_button(self._units(0.095), max(1.0, self._units(0.008)))
        x, y = self._forehead
        width, height = self._units(0.17), self._units(0.022)
        speaker = (x - width / 2, y - height / 2, x + width / 2, y + height / 2)
        _fill(self.image, self.palette["edge"], Shape("rrect", speaker, height / 2))
        camera = (x, y - self._units(0.075))
        _fill(self.image, GLASS["lens"], Shape("ellipse", _circle(camera, self._units(0.016))))

    def _camera(self) -> None:
        camera = self._forehead
        if self.landscape:
            left, top, _, bottom = self.layout.screen_box
            camera = (left - self._units(self.spec.bezels.side) / 2, (top + bottom) / 2)
        _fill(self.image, GLASS["tablet"], Shape("ellipse", _circle(camera, self._units(0.009))))

    def _punch_hole(self) -> None:
        """Draw the duo outer display's round front camera and lens in the top-right corner."""
        _, top, right, _ = self.layout.screen_box
        center = (right - self._units(0.095), top + self._units(0.103))
        _fill(self.image, GLASS["island"], Shape("ellipse", _circle(center, self._units(0.041))))
        _fill(self.image, GLASS["lens"], Shape("ellipse", _circle(center, self._units(0.016))))

    def _tablet_home(self) -> None:
        lens = _circle(self._forehead, self._units(0.009))
        _fill(self.image, GLASS["tablet"], Shape("ellipse", lens))
        self._home_button(self._units(0.04), max(1.0, self._units(0.004)))

    def _home_button(self, radius: float, ring: float) -> None:
        _fill(self.image, self.palette["edge"], Shape("ellipse", _circle(self._chin, radius)))
        _fill(self.image, self.front, Shape("ellipse", _circle(self._chin, radius - ring)))


class _Laptop:
    """Draws a MacBook lid with its camera notch, above a deck and hinge."""

    def __init__(self, layout: _Layout, palette: dict[str, Color]):
        self.layout, self.palette = layout, palette
        self.image = Image.new("RGBA", layout.size)
        self.radius = 0.022 * layout.unit

    def lid(self) -> None:
        """Draw the lid's metal edge, band and black glass, rounded at the top."""
        unit, (left, top, right, bottom) = self.layout.unit, self.layout.body
        edge, rim = max(1.0, 0.003 * unit), max(1.0, 0.005 * unit)
        for color, inset in (("edge", 0.0), ("band", edge), ("bezel", rim)):
            box = (left + inset, top + inset, right - inset, bottom)
            _fill(
                self.image,
                self.palette[color],
                Shape("rrect", box, self.radius - inset, TOP_CORNERS),
            )

    def screen(self, content: Image.Image) -> None:
        """Paste the screenshot below the camera notch, then draw the camera."""
        unit, (width, _) = self.layout.unit, self.layout.screen
        notch_w, notch_h = 0.122 * unit, 0.022 * unit
        notch = (width / 2 - notch_w / 2, -notch_h, width / 2 + notch_w / 2, notch_h)
        shapes = [
            Shape("rrect", (0, 0, *self.layout.screen), 0.009 * unit, TOP_CORNERS),
            Shape("rrect", notch, notch_h / 2.5, clear=True),
        ]
        _paste(self.image, content, self.layout.origin, shapes)
        x, y = self.layout.origin
        housing_top = self.layout.body[1] + max(1.0, 0.005 * unit)
        camera = (x + width / 2, (housing_top + y + notch_h) / 2)
        _fill(self.image, GLASS["laptop"], Shape("ellipse", _circle(camera, 0.006 * unit)))

    def deck(self) -> None:
        """Draw the deck's rounded front edge, shaded lip, thumb groove and hinge."""
        width, height = self.layout.size
        lid_left, _, lid_right, lid_h = self.layout.body
        deck_h = height - lid_h

        def rounded_below(box: Box, radius: float, cut: float) -> tuple[Shape, Shape]:
            # A rounded rectangle extended upward, then cleared above ``cut``.
            above = (box[0], box[1] - deck_h, box[2], box[3])
            return (
                Shape("rrect", above, radius, BOTTOM_CORNERS),
                Shape("rect", (box[0], above[1], box[2], cut), clear=True),
            )

        deck = (0, lid_h, width, height)
        _fill(self.image, self.palette["deck"], *rounded_below(deck, deck_h * 0.9, lid_h))
        lip = rounded_below(deck, deck_h * 0.9, lid_h + deck_h * 0.55)
        _fill(self.image, self.palette["deck_shade"], *lip)
        groove_w = 0.15 * (lid_right - lid_left)
        groove = (width / 2 - groove_w / 2, lid_h, width / 2 + groove_w / 2, lid_h + deck_h * 0.42)
        _fill(self.image, self.palette["deck_shade"], *rounded_below(groove, deck_h * 0.35, lid_h))
        hinge_h = max(1.0, 0.006 * self.layout.unit)
        hinge = (lid_left + self.radius, lid_h - 1, lid_right - self.radius, lid_h - 1 + hinge_h)
        _fill(self.image, self.palette["edge"], Shape("rect", hinge))


def _fit_phone(spec: Spec, aspect: float, box: tuple[int, int], framed: bool) -> _Layout:
    """The largest portrait layout of ``spec`` whose screen has ``aspect`` (long/short)."""
    bezels = spec.bezels if framed else NO_BEZELS
    protrusion = 0.009 if framed and spec.buttons != "none" else 0
    above = protrusion if spec.buttons in TOP_BUTTONS else 0
    spine = 0.028 if framed and spec.spine else 0
    width = 1 + 2 * bezels.side + 2 * protrusion + spine
    height = aspect + bezels.top + bezels.bottom + above
    unit = max(1, int(min(box[0] / width, box[1] / height)))
    layout = partial(
        _phone_layout,
        aspect=aspect,
        bezels=bezels,
        buttons=Protrusion(protrusion, above),
        spine=spine,
    )
    return _largest(layout, unit, box)


def _phone(
    screenshot: Image.Image,
    screen_size: tuple[int, int],
    box: tuple[int, int],
    style: DeviceStyle,
    landscape: bool,
) -> Image.Image:
    key = "tablet-home" if style.hardware == "home" and style.platform == "ipad" else style.hardware
    spec = SPECS.get(key, SPECS["plain"])
    if style.fit == "cover":
        aspect = max(screen_size) / min(screen_size)
    else:
        aspect = max(screenshot.size) / max(1, min(screenshot.size))
    framed = style.frame != "none"
    layout = _fit_phone(spec, aspect, box, framed)
    phone = _Phone(layout, spec, _device_palette(style), landscape)
    content = _content(screenshot, layout.screen, style.fit)
    if not framed:
        phone.screen(content, max(spec.screen_radius, 0.02) * layout.unit)
        return phone.image
    phone.shell()
    phone.screen(content, spec.screen_radius * layout.unit)
    phone.cutout()
    return phone.image


def _bare(
    screenshot: Image.Image,
    box: tuple[int, int],
    aspect: float,
    fit: str,
    radius: Callable[[tuple[int, int]], float],
) -> Image.Image:
    """The screenshot alone, rounded, as large as ``box`` allows at ``aspect`` (width / height)."""
    width = min(box[0], box[1] * aspect)
    screen = (max(1, int(width)), max(1, int(width / aspect)))
    image = Image.new("RGBA", screen)
    _paste(
        image,
        _content(screenshot, screen, fit),
        (0, 0),
        [Shape("rrect", (0, 0, *screen), radius(screen))],
    )
    return image


def _laptop(screenshot: Image.Image, box: tuple[int, int], style: DeviceStyle) -> Image.Image:
    aspect = (
        LAPTOP_DISPLAY if style.fit == "cover" else screenshot.width / max(1, screenshot.height)
    )
    if style.frame == "none":
        return _bare(screenshot, box, aspect, style.fit, lambda screen: 0.008 * screen[0])
    width = (1 + 2 * LID.side) * (1 + 2 * DECK_OVERHANG)
    height = 1 / aspect + LID.top + LID.bottom + DECK_HEIGHT
    unit = max(1, int(min(box[0] / width, box[1] / height)))
    layout = _largest(partial(_laptop_layout, aspect=aspect), unit, box)
    laptop = _Laptop(layout, _device_palette(style))
    laptop.lid()
    laptop.screen(_content(screenshot, layout.screen, style.fit))
    laptop.deck()
    return laptop.image


def render_device(
    source: Image.Image, screen_size: tuple[int, int], box: tuple[int, int], style: DeviceStyle
) -> Image.Image:
    """The device for ``source`` fitted in ``box``; custom sizes get only rounded corners."""
    if style.platform == "custom":
        aspect = source.width / max(1, source.height)
        return _bare(source, box, aspect, "contain", lambda screen: 0.025 * min(screen))
    if style.platform == "mac":
        return _laptop(source, box, style)
    if source.width <= source.height:
        return _phone(source, screen_size, box, style, landscape=False)
    # Landscape screenshots are drawn on a portrait body, then rotated clockwise back.
    screenshot = source.transpose(Image.Transpose.ROTATE_90)
    body = _phone(screenshot, screen_size, (box[1], box[0]), style, landscape=True)
    return body.transpose(Image.Transpose.ROTATE_270)
