"""Read the bundled target catalog independently of the working directory."""

import json
import re
from functools import cache
from importlib.resources import files
from typing import Any

# Custom sizes use ``custom.<width>x<height>`` and have no device mockup.
CUSTOM_TARGET = re.compile(r"custom\.([1-9][0-9]*)x([1-9][0-9]*)")
CUSTOM_SIDES = (64, 8192)
CUSTOM_MAX_PIXELS = 24_000_000


def load_catalog() -> dict[str, Any]:
    """A fresh copy of the packaged catalog, including its source metadata."""
    resource = files("jamshoot").joinpath("data", "targets.json")
    return json.loads(resource.read_text(encoding="utf-8"))


@cache
def _catalog_targets() -> dict[str, dict[str, Any]]:
    return {target["id"]: target for target in load_catalog()["targets"]}


def custom_target(width: int, height: int) -> dict[str, Any]:
    """The target dict for a custom size: no display groups, plain hardware."""
    return {
        "id": f"custom.{width}x{height}",
        "platform": "custom",
        "width": width,
        "height": height,
        "orientation": "landscape" if width > height else "portrait",
        "displayGroups": [],
        "hardware": "plain",
    }


def find_target(target_id: str) -> dict[str, Any] | None:
    """A copy of the catalog target or valid custom size ``target_id``; None when unknown."""
    if target_id in _catalog_targets():
        return json.loads(json.dumps(_catalog_targets()[target_id]))
    match = CUSTOM_TARGET.fullmatch(target_id)
    if not match:
        return None
    width, height = (int(side) for side in match.groups())
    low, high = CUSTOM_SIDES
    if not (low <= width <= high and low <= height <= high) or width * height > CUSTOM_MAX_PIXELS:
        return None
    return custom_target(width, height)
