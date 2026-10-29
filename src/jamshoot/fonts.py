"""Default font for text fields (headline, subtitle, feature label) that set no font family.

``JAMSHOOT_FONT`` points to a TTF, OTF or TTC file. When it is unset, the first installed
family from the platform's sans-serif list is used, with the face picked by weight. Fonts
are never downloaded.
"""

import os
import sys
from pathlib import Path

from jamshoot.core.project import ProjectError
from jamshoot.typefaces import pick_face, system_faces

# The platform's usual sans-serif families, in order of preference.
DEFAULT_FAMILIES = {
    "darwin": ("Helvetica Neue", "Helvetica", "Arial"),
    "win32": ("Segoe UI", "Arial"),
}
OTHER_FAMILIES = ("DejaVu Sans", "Noto Sans", "Liberation Sans", "Arial")


def default_families() -> tuple[str, ...]:
    """The families tried, in order, when ``JAMSHOOT_FONT`` is not set."""
    return DEFAULT_FAMILIES.get(sys.platform, OTHER_FAMILIES)


def default_face(weight: float | None = None) -> tuple[str, int]:
    """The default font file and face index for ``weight``; ProjectError if none is available."""
    configured = os.environ.get("JAMSHOOT_FONT")
    if configured:
        path = Path(configured).expanduser()
        if not path.is_file():
            raise ProjectError(f"Font unavailable: JAMSHOOT_FONT names no file: {path}")
        return str(path), 0
    faces = system_faces()
    for family in default_families():
        face = pick_face(faces, family, 400 if weight is None else weight)
        if face is not None:
            return face.path, face.number
    raise ProjectError(
        "Font unavailable: none of " + ", ".join(default_families()) + " is installed;"
        " install one, set JAMSHOOT_FONT to a TTF/OTF/TTC file or choose a font in"
        " Project → Typography"
    )
