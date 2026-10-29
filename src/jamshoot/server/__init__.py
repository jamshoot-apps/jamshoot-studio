"""Optional loopback Studio: a project library with the CLI's validation and rendering."""

import secrets
import webbrowser
from wsgiref.simple_server import WSGIRequestHandler, make_server

from bottle import Bottle

from jamshoot.core.project import ProjectError
from jamshoot.library import InPlace, ProjectLibrary
from jamshoot.server.assets import icon_asset, pattern_preview, static_asset
from jamshoot.server.projects import ProjectsAPI
from jamshoot.server.responses import Session, guard
from jamshoot.settings import Homes, studio_home

__all__ = ["Session", "create_app", "serve"]


class RequestHandler(WSGIRequestHandler):
    """Request handler that drops stalled clients so the single-threaded server keeps serving."""

    timeout = 5

    def handle(self) -> None:
        """Handle the request; a timeout closes it without a traceback."""
        try:
            super().handle()
        except TimeoutError:
            pass


def create_app(library: ProjectLibrary, session: Session) -> Bottle:
    """The Studio app: start screen, project editors, API and static files, behind the guard."""
    app = Bottle()
    guard(app, session)
    app.route("/vendor/ionicons/<asset>", "GET", icon_asset)
    app.route("/pattern-preview/<pattern>", "GET", pattern_preview)
    ProjectsAPI(library, session).register(app)
    app.route("/<asset:path>", "GET", static_asset)
    return app


def serve(
    project: InPlace | None = None,
    *,
    homes: Homes | None = None,
    port: int = 8765,
    max_files: int = 1000,
    open_browser: bool = False,
) -> None:
    """Run Studio on IPv4 loopback until Ctrl-C; ProjectError for a bad port or failed start.

    ``project`` is opened in place for this run.
    """
    if not 0 <= port <= 65535:
        raise ProjectError("Port must be between 0 and 65535")
    library = ProjectLibrary(*studio_home(*(homes or Homes())))
    opened = library.open_in_place(*project) if project is not None else None
    try:
        with make_server("127.0.0.1", port, Bottle(), handler_class=RequestHandler) as server:
            origin = f"http://127.0.0.1:{server.server_port}"
            session = Session(secrets.token_hex(32), origin, max_files)
            server.set_app(create_app(library, session))
            print(f"JamShoot Studio: {origin}", flush=True)
            print(f"Projects: {library.folder}", flush=True)
            if opened:
                print(f"Project: {origin}/project/{opened['id']}", flush=True)
                print(f"Export directory: {library.output(opened['id'])}", flush=True)
            if open_browser:
                webbrowser.open(f"{origin}/project/{opened['id']}" if opened else origin)
            server.serve_forever()
    except OSError as error:
        raise ProjectError(f"Cannot start studio: {error}") from error
    except KeyboardInterrupt:
        pass
