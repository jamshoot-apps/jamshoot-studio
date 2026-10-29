"""Studio settings: packaged defaults in ``data/settings.json``, overridden per user.

The user's file lives in the operating system's settings folder, or at
``$JAMSHOOT_SETTINGS``. Studio writes it when a setting is changed in the browser.
"""

import json
import os
import sys
import tempfile
from importlib.resources import files
from pathlib import Path
from typing import Any, NamedTuple

from jamshoot.core.project import ProjectError, parse_json

APP_FOLDER = "JamShoot Studio"


def settings_path() -> Path:
    """``$JAMSHOOT_SETTINGS``, else ``settings.json`` in the system's settings folder."""
    if override := os.environ.get("JAMSHOOT_SETTINGS"):
        return Path(override).expanduser()
    if sys.platform == "darwin":
        folder = Path.home() / "Library/Application Support" / APP_FOLDER
    elif sys.platform == "win32":
        folder = Path(os.environ.get("APPDATA") or Path.home() / "AppData/Roaming") / APP_FOLDER
    else:
        config = os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
        folder = Path(config) / "jamshoot-studio"
    return folder / "settings.json"


def default_settings() -> dict[str, Any]:
    """The packaged defaults from ``data/settings.json``."""
    resource = files("jamshoot").joinpath("data", "settings.json")
    return dict(json.loads(resource.read_text("utf-8")))


def saved_settings() -> dict[str, Any]:
    """The user's saved settings, or {} without a file; ProjectError if unreadable or invalid."""
    path = settings_path()
    try:
        data = parse_json(path.read_bytes())
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, ProjectError) as error:
        raise ProjectError(f"Cannot read Studio settings {path}: {error}") from error
    if not isinstance(data, dict):
        raise ProjectError(f"Studio settings {path} must hold a JSON object")
    return data


def save_settings(changes: dict[str, Any]) -> None:
    """Merge ``changes`` into the user's file, replacing it in one step."""
    path = settings_path()
    data = saved_settings() | changes
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=".settings-", delete=False
        ) as handle:
            temporary = Path(handle.name)
            json.dump(data, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        temporary.replace(path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


class Homes(NamedTuple):
    """The ``--home`` and ``--fallback-home`` folders passed to :func:`studio_home`."""

    home: Path | None = None
    fallback: Path | None = None


def studio_home(home: Path | None = None, fallback: Path | None = None) -> tuple[Path, str]:
    """Studio's home folder and the source that chose it, as ``(folder, source)``.

    First set wins, with its ``source``: ``home`` (``--home``), ``$JAMSHOOT_HOME``
    (``JAMSHOOT_HOME``), the saved setting (``settings``), ``fallback``, then ``default``.
    """
    if home is not None:
        return home.expanduser(), "--home"
    if environment := os.environ.get("JAMSHOOT_HOME"):
        return Path(environment).expanduser(), "JAMSHOOT_HOME"
    if saved := saved_settings().get("home"):
        return Path(str(saved)).expanduser(), "settings"
    if fallback is not None:
        return fallback.expanduser(), "fallback"
    return Path(default_settings()["home"]).expanduser(), "default"
