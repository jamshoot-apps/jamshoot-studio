"""Studio's packaged files: its own scripts and styles, vendored icons and pattern tiles."""

import json
import re
from collections.abc import Iterator
from functools import cache
from importlib.resources.abc import Traversable
from pathlib import Path

from bottle import HTTPResponse, request

from jamshoot.core.project import load_schema
from jamshoot.render.background import render_background
from jamshoot.render.export import png_bytes
from jamshoot.server.responses import WEB, fail, png

PATTERN_TILE = (160, 96)
COLOR = re.compile(r"^[0-9a-fA-F]{6}$")
STATIC_TYPES = {".js": "text/javascript", ".css": "text/css", ".svg": "image/svg+xml"}


def _static_files(root: Traversable, prefix: str) -> Iterator[tuple[str, str]]:
    """``(prefix + path, MIME type)`` for each JS, CSS and SVG file under ``root``."""
    for item in root.iterdir():
        name = prefix + item.name
        if item.is_dir():
            yield from _static_files(item, name + "/")
        elif mime := STATIC_TYPES.get(Path(item.name).suffix):
            yield name, mime


# Request paths must match this finite allowlist; vendor has its own manifest.
STATIC = {
    name: mime
    for folder in ("pages", "features", "shared", "assets")
    for name, mime in _static_files(WEB.joinpath(folder), folder + "/")
}


@cache
def _icons() -> frozenset[str]:
    manifest = WEB.joinpath("vendor", "ionicons", "manifest.json").read_text("utf-8")
    return frozenset(json.loads(manifest)["files"])


def static_asset(asset: str) -> HTTPResponse:
    """The packaged file at ``asset``; 404 unless it is in ``STATIC``."""
    mime = STATIC.get(asset)
    if mime is None:
        fail(404, "Resource unavailable")
    return HTTPResponse(
        WEB.joinpath(asset).read_text("utf-8"), content_type=f"{mime}; charset=utf-8"
    )


def icon_asset(asset: str) -> HTTPResponse:
    """The vendored icon or license file at ``asset``; 404 unless the manifest lists it."""
    if asset not in _icons():
        fail(404, "Resource unavailable")
    mime = "image/svg+xml" if asset.endswith(".svg") else "text/plain"
    content = WEB.joinpath("vendor", "ionicons", asset).read_bytes()
    return HTTPResponse(content, content_type=f"{mime}; charset=utf-8")


def pattern_preview(pattern: str) -> HTTPResponse:
    """A PNG tile of ``pattern``; optional ``top``, ``bottom``, ``accent`` and ``seed`` style it."""
    if pattern not in load_schema()["$defs"]["pattern"]["enum"]:
        fail(404, "Resource unavailable")
    colors = {}
    for key in ("top", "bottom", "accent"):
        value = request.query.get(key)
        if value is not None:
            if not COLOR.match(value):
                fail(400, f"{key} must be RRGGBB")
            colors[key] = "#" + value.lower()
    seed = request.query.getunicode("seed") or "preview"
    if len(seed) > load_schema()["$defs"]["text"]["maxLength"]:
        fail(400, "Seed is too long")
    style = {"pattern": pattern, "seed": seed, "colors": colors}
    with render_background(PATTERN_TILE, style) as image:
        return png(png_bytes(image))
