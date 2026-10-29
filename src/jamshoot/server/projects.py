"""The start screen's API: projects with thumbnails and zip import/export, and settings."""

from pathlib import Path

from bottle import Bottle, HTTPResponse

from jamshoot.core.planning import plan_project
from jamshoot.core.project import parse_json, validate_project
from jamshoot.library import MAX_ARCHIVE_BYTES, ProjectLibrary, revision
from jamshoot.server.editor import EditorAPI, thumbnail_png
from jamshoot.server.responses import (
    Session,
    endpoint,
    fail,
    json_response,
    page,
    png,
    read_body,
    read_json,
)
from jamshoot.settings import save_settings, settings_path


class ProjectsAPI:
    """The project library behind the start screen, plus an editor API per project."""

    def __init__(self, library: ProjectLibrary, session: Session):
        self.library, self.session = library, session

    def register(self, app: Bottle) -> None:
        """Mount the start screen, its API, and each project's editor page and API."""
        app.route("/", "GET", lambda: page("pages/home/home.html", self.session.token))
        app.route("/project/<pid>", "GET", self.editor)
        for method, path, callback in (
            ("GET", "/api/projects", self.list_projects),
            ("POST", "/api/projects", self.create),
            ("POST", "/api/projects/import", self.import_archive),
            ("DELETE", "/api/projects/<pid>", self.remove),
            ("GET", "/api/projects/<pid>/archive", self.export_archive),
            ("GET", "/api/projects/<pid>/thumbnail", self.thumbnail),
            ("GET", "/api/settings", self.settings),
            ("PUT", "/api/settings", self.save_settings),
        ):
            app.route(path, method, endpoint(callback))
        EditorAPI(self.resolve, self.session.max_files).register(app, "/api/projects/<pid>")

    def resolve(self, pid: str) -> tuple[Path, Path]:
        """The project's ``(project.json, export directory)``; responds 404 for an unknown id."""
        try:
            return self.library.path(pid), self.library.output(pid)
        except KeyError:
            fail(404, "Unknown project")

    def editor(self, pid: str) -> HTTPResponse:
        """The editor page for project ``pid``; 404 for an unknown id."""
        self.resolve(pid)
        return page("pages/editor/editor.html", self.session.token, f"/api/projects/{pid}")

    def list_projects(self) -> HTTPResponse:
        """Every project card (opened first, then newest edit first) and the projects folder."""
        projects = self.library.projects()
        return json_response({"projects": projects, "home": str(self.library.folder)})

    def create(self) -> HTTPResponse:
        """Create a starter project from ``name`` and ``platform``; 400 unless both are strings."""
        data = read_json()
        name, platform = data.get("name"), data.get("platform")
        if not isinstance(name, str) or not isinstance(platform, str):
            fail(400, "Expected a project name and platform")
        return json_response(self.library.create(name, platform), 201)

    def import_archive(self) -> HTTPResponse:
        """Unpack an uploaded project .zip into a new project folder."""
        return json_response(self.library.import_archive(read_body(MAX_ARCHIVE_BYTES)), 201)

    def export_archive(self, pid: str) -> HTTPResponse:
        """The project folder as a .zip download."""
        self.resolve(pid)
        name, content = self.library.export_archive(pid)
        return HTTPResponse(
            content,
            content_type="application/zip",
            headers={"Content-Disposition": f'attachment; filename="{name}"'},
        )

    def remove(self, pid: str) -> HTTPResponse:
        """Forget an opened project, or move a project folder to the trash."""
        self.resolve(pid)
        return json_response(self.library.remove(pid))

    def settings(self) -> HTTPResponse:
        """The Studio ``home``, its ``source`` (what chose it) and the settings ``file`` path."""
        return json_response(
            {
                "home": str(self.library.home),
                "source": self.library.source,
                "file": str(settings_path()),
            }
        )

    def save_settings(self) -> HTTPResponse:
        """Switch to the JSON ``home`` folder and save it for later runs; 400 unless absolute."""
        home = read_json().get("home")
        if not isinstance(home, str) or not home.strip():
            fail(400, "Enter the Studio folder")
        path = Path(home.strip()).expanduser()
        if not path.is_absolute():
            fail(400, "Enter a full path, such as ~/JamShoot")
        folder = ProjectLibrary.prepare(path)
        save_settings({"home": str(folder.parent)})
        self.library.move(folder)
        return self.settings()

    def thumbnail(self, pid: str) -> HTTPResponse:
        """The project's first planned file as a PNG thumbnail, cached per revision."""
        project_path, _ = self.resolve(pid)
        content = project_path.read_bytes()
        tag = revision(content)
        cached = self.library.thumbnail(pid, tag)
        if cached is None:
            project = validate_project(parse_json(content), project_path)
            job = plan_project(project, max_files=self.session.max_files)["files"][0]
            cached = thumbnail_png(job)
            self.library.store_thumbnail(pid, tag, cached)
        return png(cached)
