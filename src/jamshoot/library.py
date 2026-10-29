"""Studio's project library: one folder per project under ``<home>/projects``.

The folder name is the project id; removed projects move to ``<home>/trash``.
"""

import hashlib
import io
import re
import shutil
import zipfile
from datetime import UTC, datetime
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple
from uuid import uuid4

from jamshoot.catalog import find_target
from jamshoot.core.project import ProjectError, load_project, parse_json, project_assets
from jamshoot.core.starter import STARTER_TARGETS, init_project

MAX_PROJECTS = 500
MAX_ARCHIVE_FILES = 2000
MAX_ARCHIVE_BYTES = 268_435_456
PROJECT_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,99}")


class InPlace(NamedTuple):
    """A project.json to open where it is, and its export directory (None: the default)."""

    path: Path
    output: Path | None = None


def _projects_folder(home: str | Path) -> Path:
    """``<home>/projects``, created when missing; raises ProjectError if that fails."""
    folder = Path(home).expanduser().resolve() / "projects"
    try:
        folder.mkdir(parents=True, exist_ok=True)
    except OSError as error:
        raise ProjectError(f"Cannot create Studio home {folder.parent}: {error}") from error
    return folder


def revision(content: bytes) -> str:
    """The SHA-256 hex digest of a saved project file's ``content``, used as its revision."""
    return hashlib.sha256(content).hexdigest()


def _slug(name: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:40].strip("-")
    return slug or "project"


def _project_members(archive: zipfile.ZipFile) -> list[tuple[PurePosixPath, zipfile.ZipInfo]]:
    """``(relative path, member)`` for each safe file under the shallowest ``project.json``."""
    files = [
        member
        for member in archive.infolist()
        if not member.is_dir()
        and not member.filename.startswith("__MACOSX/")
        and PurePosixPath(member.filename).name != ".DS_Store"
    ]
    roots = sorted(
        (
            member.filename.removesuffix("project.json")
            for member in files
            if PurePosixPath(member.filename).name == "project.json"
        ),
        key=len,
    )
    if not roots or roots[0].count("/") > 1:
        raise ProjectError("The archive needs project.json at its top level or in one folder")
    members = []
    for member in files:
        if not member.filename.startswith(roots[0]):
            continue
        relative = PurePosixPath(member.filename.removeprefix(roots[0]))
        if "\\" in member.filename or relative.is_absolute() or ".." in relative.parts:
            raise ProjectError(f"Unsafe path in archive: {member.filename}")
        if relative.parts[0] != "exports":
            members.append((relative, member))
    if len(members) > MAX_ARCHIVE_FILES or sum(m.file_size for _, m in members) > MAX_ARCHIVE_BYTES:
        raise ProjectError(
            f"Archives may hold at most {MAX_ARCHIVE_FILES} files and "
            f"{MAX_ARCHIVE_BYTES // 1_048_576} MB"
        )
    return members


class ProjectLibrary:
    """The project folders in ``<home>/projects``, plus projects opened in place for one run."""

    def __init__(self, home: str | Path, source: str = "--home"):
        self.folder = _projects_folder(home)
        self.home = self.folder.parent
        # Define the home: either through --home, JAMSHOOT_HOME, settings, fallback or default.
        self.source = source
        # Projects opened from the CLI stay where they are and should be forgotten on exit.
        self.opened: dict[str, tuple[Path, Path | None]] = {}
        self.thumbnails: dict[str, tuple[str, bytes]] = {}

    @staticmethod
    def prepare(home: str | Path) -> Path:
        """``home``'s ``projects`` folder, created now so a bad home fails before :meth:`move`."""
        return _projects_folder(home)

    def move(self, folder: Path) -> None:
        """Switch to ``folder`` from :meth:`prepare`; opened projects and their thumbnails stay."""
        self.folder = folder
        self.home, self.source = folder.parent, "settings"
        self.thumbnails = {
            key: self.thumbnails[key] for key in self.thumbnails if key in self.opened
        }

    def _folders(self) -> list[str]:
        return [
            path.parent.name
            for path in self.folder.glob("*/project.json")
            if PROJECT_ID.fullmatch(path.parent.name)
        ]

    def path(self, project_id: str) -> Path:
        """The project's ``project.json``; unknown ids raise ``KeyError``."""
        if project_id in self.opened:
            return self.opened[project_id][0]
        path = self.folder / project_id / "project.json"
        if not PROJECT_ID.fullmatch(project_id) or not path.is_file():
            raise KeyError(project_id)
        return path

    def output(self, project_id: str) -> Path:
        """The ``--out`` directory of an opened project, else ``exports/export`` in its folder."""
        _, output = self.opened.get(project_id, (None, None))
        if output:
            return output
        return self.path(project_id).parent / "exports" / "export"

    def _summary(self, project_id: str) -> dict[str, Any]:
        """The start-screen card for ``project_id``; an unreadable project gets an ``error``."""
        path = self.path(project_id)
        item: dict[str, Any] = {
            "id": project_id,
            "path": str(path),
            "managed": project_id not in self.opened,
        }
        try:
            content = path.read_bytes()
            data = parse_json(content)
            item |= {
                "name": data["project"]["name"],
                "slides": len(data["slides"]),
                "locales": len(data["locales"]),
                "platforms": sorted(
                    {
                        (find_target(target) or {}).get("platform", "unknown")
                        for target in data["targets"]
                    }
                ),
                "updatedAt": datetime.fromtimestamp(path.stat().st_mtime, UTC).isoformat(
                    timespec="seconds"
                ),
                "revision": revision(content),
            }
        except (OSError, ProjectError, KeyError, TypeError, ValueError) as error:
            item |= {"name": path.parent.name, "error": f"Project unavailable: {error}"}
        return item

    def projects(self) -> list[dict[str, Any]]:
        """Projects opened for this run first, then folders, most recently edited first."""
        folders = [self._summary(project_id) for project_id in self._folders()]
        folders.sort(key=lambda item: item.get("updatedAt", ""), reverse=True)
        return [self._summary(project_id) for project_id in self.opened] + folders

    def get(self, project_id: str) -> dict[str, Any]:
        """The start-screen card for one project."""
        return self._summary(project_id)

    def _new_folder(self, name: str) -> Path:
        if len(self._folders()) >= MAX_PROJECTS:
            raise ProjectError(f"Studio supports at most {MAX_PROJECTS} projects")
        return self.folder / f"{_slug(name)}-{uuid4().hex[:6]}"

    def create(self, name: str, platform: str) -> dict[str, Any]:
        """Create a starter project for ``platform`` and return its card."""
        name = name.strip()
        if not name or len(name) > 200:
            raise ProjectError("Project name must contain 1–200 characters")
        if platform not in STARTER_TARGETS:
            raise ProjectError("Choose iPhone, iPad or Mac")
        path = init_project(self._new_folder(name), name=name, platform=platform)
        return self.get(path.parent.name)

    def export_archive(self, project_id: str) -> tuple[str, bytes]:
        """``(<name>.zip, bytes)`` holding ``project.json``, its images, ``assets/`` and schema."""
        project = load_project(self.path(project_id))
        source = project.path.parent
        files = {project.path, *project_assets(project)}
        if (source / "assets").is_symlink() or any(
            item.is_symlink() for item in (source / "assets").rglob("*")
        ):
            raise ProjectError("Archive files must stay inside the project folder")
        files |= {item for item in (source / "assets").rglob("*") if item.is_file()}
        if (source / "project.schema.json").is_file():
            files.add(source / "project.schema.json")
        name = _slug(project.data["project"]["name"])
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            for item in sorted(files):
                if item.is_symlink() or not item.resolve().is_relative_to(source):
                    raise ProjectError("Archive files must stay inside the project folder")
                archive.write(item, f"{name}/{item.relative_to(source).as_posix()}")
        return f"{name}.zip", buffer.getvalue()

    def import_archive(self, content: bytes) -> dict[str, Any]:
        """Unpack a project .zip into a new folder and return its card."""
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                members = _project_members(archive)
                staging = self.folder / f".import-{uuid4().hex}"
                try:
                    for relative, member in members:
                        target = staging.joinpath(*relative.parts)
                        target.parent.mkdir(parents=True, exist_ok=True)
                        with archive.open(member) as source, target.open("wb") as copy:
                            shutil.copyfileobj(source, copy)
                    project = load_project(staging / "project.json")
                    directory = self._new_folder(project.data["project"]["name"])
                    staging.rename(directory)
                finally:
                    shutil.rmtree(staging, ignore_errors=True)
        except zipfile.BadZipFile as error:
            raise ProjectError(f"Expected a project .zip archive: {error}") from error
        return self.get(directory.name)

    def open_in_place(self, path: str | Path, output: str | Path | None = None) -> dict[str, Any]:
        """Open ``path`` in place for this run and return its card; reopening keeps its id."""
        project = load_project(path).path
        if project.parent.parent == self.folder:
            return self.get(project.parent.name)
        project_id = next(
            (key for key, (known, _) in self.opened.items() if known == project), uuid4().hex[:12]
        )
        destination = (
            Path(output).absolute() if output else self.opened.get(project_id, ("", None))[1]
        )
        self.opened[project_id] = (project, destination)
        return self.get(project_id)

    def remove(self, project_id: str) -> dict[str, Any]:
        """Forget an opened project or move its folder to ``<home>/trash``; KeyError if unknown."""
        directory = self.path(project_id).parent
        self.thumbnails.pop(project_id, None)
        if self.opened.pop(project_id, None):
            return {"removed": project_id, "movedTo": None}
        trash = self.home / "trash"
        trash.mkdir(exist_ok=True)
        moved = trash / f"{project_id}-{datetime.now(UTC):%Y%m%d%H%M%S}"
        shutil.move(directory, moved)
        return {"removed": project_id, "movedTo": str(moved)}

    def thumbnail(self, project_id: str, tag: str) -> bytes | None:
        """The cached PNG thumbnail for ``project_id`` if it is for revision ``tag``, else None."""
        cached = self.thumbnails.get(project_id)
        return cached[1] if cached and cached[0] == tag else None

    def store_thumbnail(self, project_id: str, tag: str, png: bytes) -> None:
        """Cache ``png`` as the thumbnail for ``project_id`` at revision ``tag``."""
        self.thumbnails[project_id] = (tag, png)
