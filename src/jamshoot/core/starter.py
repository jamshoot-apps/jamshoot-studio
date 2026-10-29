"""Create a portable starter project without overwriting files."""

import json
from pathlib import Path

from PIL import Image, ImageDraw

from jamshoot.core.project import ProjectError, load_schema

# Studio starters: each platform's size in its required display group.
STARTER_TARGETS = {
    "mac": "appstore.mac.2880x1800",
    "iphone": "appstore.iphone.1179x2556",
    "ipad": "appstore.ipad.2064x2752",
}
# The CLI example is a Mac window with a sample screenshot, so it renders at once.
CLI_EXAMPLE_TARGET = "appstore.mac.1280x800"
CLI_EXAMPLE_SCREENSHOT = (1440, 900)


def _save_placeholder(path: Path, size: tuple[int, int]) -> None:
    """Save a neutral placeholder screenshot with a darker title bar to ``path``."""
    image = Image.new("RGB", size, "#e6eae8")
    bar_height = max(1, size[1] // 18)
    ImageDraw.Draw(image).rectangle((0, 0, size[0] - 1, bar_height - 1), fill="#c9d1cd")
    image.save(path, format="PNG")


def init_project(
    directory: str | Path, *, name: str = "Example App", platform: str | None = None
) -> Path:
    """Create a project in the new ``directory`` and return its ``project.json`` path.

    Without ``platform`` it is the CLI's Mac example with a placeholder screenshot.
    """
    directory = Path(directory).resolve()
    if platform is not None and platform not in STARTER_TARGETS:
        raise ProjectError(f"Unsupported starter platform: {platform}")
    try:
        directory.mkdir(parents=True, exist_ok=False)
        (directory / "assets").mkdir()
        assets = {}
        if platform is None:
            _save_placeholder(directory / "assets/screenshot.png", CLI_EXAMPLE_SCREENSHOT)
            assets = {"mac": "./assets/screenshot.png"}
        slide = {
            "id": "overview",
            "copy": {"en-US": {"headline": "Your app at a glance"}},
            "assets": assets,
        }
        if platform:
            slide["name"] = "Slide 1"
        data = {
            "$schema": "./project.schema.json",
            "version": 1,
            "project": {"name": name},
            "targets": [STARTER_TARGETS[platform] if platform else CLI_EXAMPLE_TARGET],
            "locales": ["en-US"],
            "defaults": {
                "layout": "auto" if platform else "window-top",
                "pattern": "dots",
                "seed": "launch",
            },
            "slides": [slide],
        }
        (directory / "project.schema.json").write_text(
            json.dumps(load_schema(), indent=2) + "\n", encoding="utf-8"
        )
        project = directory / "project.json"
        project.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
        return project
    except OSError as error:
        raise ProjectError(f"Cannot initialize project {directory}: {error}") from error
