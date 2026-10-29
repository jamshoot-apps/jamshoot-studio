"""Font discovery: scan font folders for faces and resolve a family and weight to a face.

Two sources, searched in order: the project's ``assets/fonts`` (exported with the project),
then installed fonts (the platform's font folders, or ``JAMSHOOT_FONT_DIRS``). A project
using an installed family renders only on machines that have it.
"""

import os
import sys
import time
from functools import cache
from pathlib import Path
from typing import NamedTuple

from PIL import ImageFont

from jamshoot.core.project import ProjectError

FONT_SUFFIXES = {".ttf", ".otf", ".ttc"}
PROJECT_FONTS = "assets/fonts"
# Style-name words and the CSS weight they stand for; longer words are matched first.
WEIGHT_WORDS = (
    ("extralight", 200),
    ("ultralight", 200),
    ("extrabold", 800),
    ("ultrabold", 800),
    ("semibold", 600),
    ("demibold", 600),
    ("hairline", 100),
    ("medium", 500),
    ("heavy", 800),
    ("black", 900),
    ("light", 300),
    ("thin", 100),
    ("bold", 700),
)
# Faces a TrueType collection may hold before the rest are ignored.
MAX_FACES = 64
# Seconds the installed faces are reused before the font folders are looked at again.
SYSTEM_REFRESH = 30.0


class Face(NamedTuple):
    """One face of a font file; ``number`` picks it inside a collection."""

    family: str
    style: str
    weight: int
    italic: bool
    variable: bool
    path: str
    number: int


def style_weight(style: str) -> int:
    """The CSS weight a style name such as "SemiBold Italic" stands for; 400 if none."""
    words = style.lower().replace(" ", "").replace("-", "")
    return next((weight for word, weight in WEIGHT_WORDS if word in words), 400)


def _is_variable(font: ImageFont.FreeTypeFont) -> bool:
    try:
        return any(axis.get("name") == b"Weight" for axis in font.get_variation_axes())
    except OSError:
        return False


def _file_faces(path: Path) -> list[Face]:
    """Every face in font file ``path``, minus unnamed or dot-named families; none if unreadable."""
    faces = []
    count = MAX_FACES if path.suffix.lower() == ".ttc" else 1
    for index in range(count):
        try:
            font = ImageFont.truetype(str(path), size=12, index=index)
        except OSError:
            break
        family, style = font.getname()
        if not family or family.startswith("."):
            continue
        style = style or "Regular"
        faces.append(
            Face(
                family,
                style,
                style_weight(style),
                "italic" in style.lower() or "oblique" in style.lower(),
                _is_variable(font),
                str(path),
                index,
            )
        )
    return faces


def _folder_files(folder: Path) -> list[Path]:
    """Font files under ``folder``, skipping symlinks; an unreadable folder yields none."""
    try:
        return sorted(
            path
            for path in folder.rglob("*")
            if path.suffix.lower() in FONT_SUFFIXES and path.is_file() and not path.is_symlink()
        )
    except OSError:
        return []


@cache
def _cached_faces(path: str, version: tuple[int, int]) -> tuple[Face, ...]:
    """The faces of a font file, cached by its ``version`` (mtime and size)."""
    del version
    return tuple(_file_faces(Path(path)))


def folder_faces(folder: Path) -> list[Face]:
    """Every face in ``folder``'s font files."""
    faces: list[Face] = []
    for path in _folder_files(folder):
        stat = path.stat()
        faces.extend(_cached_faces(str(path), (stat.st_mtime_ns, stat.st_size)))
    return faces


def system_folders() -> list[Path]:
    """The ``JAMSHOOT_FONT_DIRS`` folders (``os.pathsep``-separated), else the platform's."""

    configured = os.environ.get("JAMSHOOT_FONT_DIRS")
    if configured is not None:
        return [Path(item).expanduser() for item in configured.split(os.pathsep) if item]
    home = Path.home()
    if sys.platform == "darwin":
        return [Path("/System/Library/Fonts"), Path("/Library/Fonts"), home / "Library/Fonts"]
    if sys.platform == "win32":
        windows = Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"
        local = Path(os.environ.get("LOCALAPPDATA", home / "AppData/Local"))
        return [windows, local / "Microsoft/Windows/Fonts"]
    return [
        Path("/usr/share/fonts"),
        Path("/usr/local/share/fonts"),
        home / ".local/share/fonts",
        home / ".fonts",
    ]


# The last scan: when, of which folders, and the faces found.
_SYSTEM: dict[tuple[str, ...], tuple[float, list[Face]]] = {}


def system_faces() -> list[Face]:
    """Every installed face, rescanned once the last scan is older than ``SYSTEM_REFRESH``."""
    folders = tuple(map(str, system_folders()))
    now = time.monotonic()
    scanned = _SYSTEM.get(folders)
    if scanned is None or now - scanned[0] > SYSTEM_REFRESH:
        _SYSTEM.clear()
        scanned = _SYSTEM[folders] = (
            now,
            [face for folder in folders for face in folder_faces(Path(folder))],
        )
    return scanned[1]


def project_faces(project_dir: Path) -> list[Face]:
    """The faces in the project's ``assets/fonts`` folder, or none when it is a symlink."""
    folder = project_dir / PROJECT_FONTS
    return [] if folder.is_symlink() else folder_faces(folder)


def families(faces: list[Face]) -> list[dict[str, object]]:
    """One entry per family, by name, with its ``styles`` and weight-axis ``variable`` flag."""
    styles: dict[str, list[str]] = {}
    variable: dict[str, bool] = {}
    for face in faces:
        names = styles.setdefault(face.family, [])
        if face.style not in names:
            names.append(face.style)
        variable[face.family] = variable.get(face.family, False) or face.variable
    return [
        {"family": family, "styles": styles[family], "variable": variable[family]}
        for family in sorted(styles, key=str.casefold)
    ]


def pick_face(faces: list[Face], family: str, weight: float) -> Face | None:
    """The family's face nearest ``weight``, preferring upright, then variable faces; or None."""
    matches = [face for face in faces if face.family.casefold() == family.casefold()]
    upright = [face for face in matches if not face.italic] or matches
    if not upright:
        return None
    variable = [face for face in upright if face.variable]
    if variable:
        return variable[0]
    return min(upright, key=lambda face: (abs(face.weight - weight), -face.weight))


def find_face(project_dir: Path, family: str, weight: float) -> Face:
    """The face for ``family`` at ``weight``, project fonts first; ProjectError if missing."""
    face = pick_face(project_faces(project_dir), family, weight) or pick_face(
        system_faces(), family, weight
    )
    if face is None:
        raise ProjectError(
            f"Font unavailable: {family} is neither in {PROJECT_FONTS} nor installed;"
            " upload it in Project → Typography"
        )
    return face
