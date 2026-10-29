"""One project's editor API: load, save, plan, preview, export and assets."""

import io
import json
import os
import re
import tempfile
from collections.abc import Callable
from pathlib import Path, PurePosixPath
from typing import Any
from uuid import uuid4

from bottle import Bottle, HTTPResponse, request
from PIL import ImageFont

from jamshoot.catalog import CUSTOM_MAX_PIXELS, CUSTOM_SIDES, custom_target, load_catalog
from jamshoot.core.appearance import (
    auto_layout,
    layout_allowed,
    layout_defaults,
    studio_appearance,
    typography_defaults,
)
from jamshoot.core.planning import plan_project
from jamshoot.core.project import (
    IMAGE_SUFFIXES,
    Project,
    load_schema,
    parse_json,
    validate_project,
)
from jamshoot.library import revision
from jamshoot.render.compositor import render_job
from jamshoot.render.export import png_bytes, render_project
from jamshoot.render.images import load_image
from jamshoot.server.responses import endpoint, fail, json_response, png, read_body, read_json
from jamshoot.typefaces import (
    FONT_SUFFIXES,
    PROJECT_FONTS,
    families,
    project_faces,
    system_faces,
)

MAX_UPLOAD_BYTES = 16_777_216
UNSAFE_NAME = re.compile(r"[^A-Za-z0-9._-]+")
THUMBNAIL_WIDTH = 480

# A project id to its (project.json, export directory).
Resolver = Callable[[str], tuple[Path, Path]]


def thumbnail_png(job: dict[str, Any]) -> bytes:
    """The rendered ``job`` as a PNG, at most ``THUMBNAIL_WIDTH`` wide and twice that tall."""
    with render_job(job) as image:
        image.thumbnail((THUMBNAIL_WIDTH, THUMBNAIL_WIDTH * 2))
        return png_bytes(image)


def _next_destination(output: Path) -> Path:
    destination, number = output, 2
    while destination.exists() or destination.is_symlink():
        destination = output.with_name(f"{output.name}-{number}")
        number += 1
    return destination


def _replace(path: Path, text: str, check: Callable[[], None]) -> None:
    """Write ``text`` to a temp file beside ``path``, then atomically replace ``path``.

    ``check`` runs before writing and before replacing; raising aborts.
    """
    check()
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=path.parent, prefix=".jamshoot-", delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(text)
        check()
        os.replace(temporary, path)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def _with_rules(target: dict[str, Any], layouts: list[str]) -> dict[str, Any]:
    """``target`` with ``autoLayout``, ``layouts`` and built-in layout and text defaults added."""
    allowed = [layout for layout in layouts if layout_allowed(layout, target)]
    size = (target["width"], target["height"])
    target["autoLayout"] = auto_layout(target)
    target["layouts"] = allowed
    explicit = [layout for layout in allowed if layout != "auto"]
    target["layoutDefaults"] = {layout: layout_defaults(layout, size) for layout in explicit}
    target["typographyDefaults"] = {
        layout: typography_defaults(layout, size) for layout in explicit
    }
    return target


def _studio_catalog(layouts: list[str]) -> dict[str, Any]:
    """The catalog with layout rules per target, plus portrait and landscape ``custom`` rules."""
    catalog = load_catalog()
    for target in catalog["targets"]:
        _with_rules(target, layouts)
    catalog["custom"] = {
        orientation: {
            key: value
            for key, value in _with_rules(custom_target(*size), layouts).items()
            if key in {"autoLayout", "layouts", "layoutDefaults", "typographyDefaults"}
        }
        for orientation, size in {"portrait": (1, 2), "landscape": (2, 1)}.items()
    }
    catalog["customSides"] = list(CUSTOM_SIDES)
    catalog["customMaxPixels"] = CUSTOM_MAX_PIXELS
    return catalog


def _snapshot(project_path: Path, output: Path) -> dict[str, Any]:
    """The editor's load data: project, revision, catalog, schema, presets, limits, output."""
    content = project_path.read_bytes()
    schema = load_schema()
    return {
        "project": validate_project(parse_json(content), project_path).data,
        "revision": revision(content),
        "catalog": _studio_catalog(schema["$defs"]["layout"]["enum"]),
        "schema": schema,
        "appearance": studio_appearance(),
        "limits": {"uploadBytes": MAX_UPLOAD_BYTES},
        "output": str(output),
    }


class EditorAPI:
    """The routes the editor page calls for one project."""

    def __init__(self, resolve: Resolver, max_files: int):
        self.resolve, self.max_files = resolve, max_files

    def register(self, app: Bottle, prefix: str) -> None:
        """Mount the editor routes under ``prefix``, whose ``<pid>`` is the project id."""
        for method, path, callback in (
            ("GET", "/project", self.load),
            ("POST", "/project", self.save),
            ("POST", "/plan", self.plan),
            ("POST", "/preview", self.preview),
            ("POST", "/export", self.export),
            ("GET", "/assets", self.assets),
            ("POST", "/assets", self.upload),
            ("GET", "/fonts", self.fonts),
            ("POST", "/fonts", self.upload_font),
        ):
            app.route(prefix + path, method, endpoint(callback))

    def _draft(self, project_path: Path, data: dict[str, Any]) -> Project:
        return validate_project(data.get("project"), project_path)

    def load(self, pid: str) -> HTTPResponse:
        """The saved project and everything the editor needs to open it."""
        return json_response(_snapshot(*self.resolve(pid)))

    def save(self, pid: str) -> HTTPResponse:
        """Validate and atomically save the draft; 409 if ``revision`` no longer matches on disk."""
        project_path, output = self.resolve(pid)
        data = read_json()
        project = self._draft(project_path, data)

        def unchanged() -> None:
            if data.get("revision") != revision(project_path.read_bytes()):
                fail(409, "Project changed on disk; reload before saving")

        text = json.dumps(project.data, ensure_ascii=True, indent=2) + "\n"
        _replace(project_path, text, unchanged)
        return json_response(_snapshot(project_path, output))

    def plan(self, pid: str) -> HTTPResponse:
        """The output files the draft would produce."""
        project_path, _ = self.resolve(pid)
        project = self._draft(project_path, read_json())
        return json_response(plan_project(project, max_files=self.max_files))

    def preview(self, pid: str) -> HTTPResponse:
        """Planned file ``index`` of the draft as a PNG, full size or as a ``thumbnail``.

        Full size sends text and screenshot boxes in ``X-JamShoot-Guides``; bad input gets 400.
        """
        project_path, _ = self.resolve(pid)
        data = read_json()
        thumbnail = data.get("thumbnail", False)
        if not isinstance(thumbnail, bool):
            fail(400, "Preview thumbnail must be true or false")
        plan = plan_project(self._draft(project_path, data), max_files=self.max_files)
        index = data.get("index")
        if (
            isinstance(index, bool)
            or not isinstance(index, int)
            or not 0 <= index < plan["fileCount"]
        ):
            fail(400, "Preview index is outside the plan")
        job = plan["files"][index]
        if thumbnail:
            return png(thumbnail_png(job))
        guides: dict[str, Any] = {}
        with render_job(job, guides) as image:
            response = png(png_bytes(image))
        # Where the text and screenshot landed, so Studio can draw spacing guides over the image.
        response.set_header("X-JamShoot-Guides", json.dumps(guides, separators=(",", ":")))
        return response

    def export(self, pid: str) -> HTTPResponse:
        """Render the draft into a fresh export directory and return its manifest."""
        project_path, output = self.resolve(pid)
        project = self._draft(project_path, read_json())
        destination = _next_destination(output)
        destination.parent.mkdir(parents=True, exist_ok=True)
        manifest = render_project(project, destination, max_files=self.max_files)
        return json_response(manifest | {"outputDirectory": str(destination)})

    def assets(self, pid: str) -> HTTPResponse:
        """The images directly in the project's ``assets`` folder, skipping symlinks."""
        project_path, _ = self.resolve(pid)
        directory = project_path.parent / "assets"
        images = []
        if directory.is_dir() and not directory.is_symlink():
            images = [
                {"path": f"assets/{path.name}", "name": path.name}
                for path in sorted(directory.iterdir())
                if path.is_file()
                and not path.is_symlink()
                and path.suffix.lower() in IMAGE_SUFFIXES
            ]
        return json_response({"assets": images})

    def upload(self, pid: str) -> HTTPResponse:
        """Save the upload as a new PNG in ``assets``, named from ``?name=``; 201 with ``path``."""
        project_path, _ = self.resolve(pid)
        image = load_image(io.BytesIO(read_body(MAX_UPLOAD_BYTES)))
        directory = project_path.parent / "assets"
        if directory.is_symlink():
            fail(400, "Upload directory must not be a symlink")
        directory.mkdir(exist_ok=True)
        name = _upload_name(directory, request.query.get("name", ""))
        with image, (directory / name).open("xb") as stream:
            image.save(stream, format="PNG")
        return json_response({"path": f"assets/{name}"}, 201)

    def fonts(self, pid: str) -> HTTPResponse:
        """The font families under ``project`` (its font folder) and ``system`` (installed)."""
        project_path, _ = self.resolve(pid)
        return json_response(
            {
                "project": families(project_faces(project_path.parent)),
                "system": families(system_faces()),
            }
        )

    def upload_font(self, pid: str) -> HTTPResponse:
        """Save an uploaded TTF, OTF or TTC in ``assets/fonts``; 201 with its ``families``."""
        project_path, _ = self.resolve(pid)
        original = request.query.get("name", "")
        suffix = PurePosixPath(original.replace("\\", "/")).suffix.lower()
        if suffix not in FONT_SUFFIXES:
            fail(400, "Font must be a .ttf, .otf or .ttc file")
        content = read_body(MAX_UPLOAD_BYTES)
        try:
            ImageFont.truetype(io.BytesIO(content), size=12)
        except OSError as error:
            fail(400, f"Not a readable font: {error}")
        directory = project_path.parent / PROJECT_FONTS
        if directory.is_symlink() or directory.parent.is_symlink():
            fail(400, "Font directory must not be a symlink")
        directory.mkdir(parents=True, exist_ok=True)
        name = _upload_name(directory, original, suffix, "font")
        with (directory / name).open("xb") as stream:
            stream.write(content)
        faces = project_faces(project_path.parent)
        added = [face.family for face in faces if Path(face.path).name == name]
        return json_response(
            {"path": f"{PROJECT_FONTS}/{name}", "families": added, "project": families(faces)},
            201,
        )


def _upload_name(
    directory: Path, original: str, suffix: str = ".png", fallback: str = "screenshot"
) -> str:
    """An unused portable file name from ``original``, numbered if taken; ``fallback`` if empty."""
    stem = UNSAFE_NAME.sub("-", PurePosixPath(original.replace("\\", "/")).stem)
    stem = stem.strip("-._")[:60] or fallback
    for number in range(1, 100):
        name = f"{stem}{suffix}" if number == 1 else f"{stem}-{number}{suffix}"
        if not (directory / name).exists():
            return name
    return f"{stem}-{uuid4().hex}{suffix}"
