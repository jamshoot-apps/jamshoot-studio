"""HTTP plumbing shared by Studio's routes: JSON responses, request bodies and the guard."""

import hmac
import json
import re
from collections.abc import Callable
from dataclasses import dataclass
from functools import wraps
from importlib.resources import files
from typing import Any, NoReturn
from urllib.parse import urljoin, urlsplit

from bottle import Bottle, HTTPResponse, request, response

from jamshoot.core.project import ProjectError, parse_json

MAX_JSON_BYTES = 1_048_576
CONTENT_SECURITY_POLICY = (
    "default-src 'self'; img-src 'self' blob:; style-src 'self'; script-src 'self'; "
    "frame-ancestors 'none'; base-uri 'none'; form-action 'none'"
)
WEB = files("jamshoot").joinpath("web")


@dataclass(frozen=True)
class Session:
    """One Studio run: its secret token, the only allowed origin and the plan limit."""

    token: str
    origin: str
    max_files: int = 1000


def json_response(data: Any, status: int = 200) -> HTTPResponse:
    """``data`` as an ASCII JSON response with ``status``."""
    return HTTPResponse(
        json.dumps(data, ensure_ascii=True),
        status=status,
        content_type="application/json; charset=utf-8",
    )


def fail(status: int, message: str) -> NoReturn:
    """Abort the request with a JSON error ``message`` at HTTP ``status``."""
    raise json_response({"error": {"code": "studio_error", "message": message}}, status)


def endpoint(function: Callable[..., HTTPResponse]) -> Callable[..., HTTPResponse]:
    """A route wrapper that returns project, file and input errors as JSON 400 responses."""

    @wraps(function)
    def guarded(*args: Any, **kwargs: Any) -> HTTPResponse:
        try:
            return function(*args, **kwargs)
        except (ProjectError, OSError, ValueError, RuntimeError) as error:
            detail: dict[str, Any] = {"code": "invalid_project", "message": str(error)}
            if isinstance(error, ProjectError) and error.issues:
                detail["details"] = error.issues
            return json_response({"error": detail}, 400)

    return guarded


def read_body(limit: int) -> bytes:
    """The request body; 413 unless it declares a length up to ``limit``, 400 if cut short."""
    length = request.content_length
    if length < 0 or length > limit:
        fail(413, f"Request must declare a body no larger than {limit} bytes")
    content = request.environ["wsgi.input"].read(length)
    if len(content) != length:
        fail(400, "Incomplete request body")
    return content


def read_json() -> dict[str, Any]:
    """The body as a strict JSON object; 415 for another content type, 400 for a non-object."""
    if request.content_type != "application/json":
        fail(415, "Expected application/json")
    data = parse_json(read_body(MAX_JSON_BYTES))
    if not isinstance(data, dict):
        fail(400, "Expected a JSON object")
    return data


def page(name: str, token: str, api: str = "") -> HTTPResponse:
    """The HTML page ``name`` with absolute links, and ``token`` and ``api`` filled in."""
    html = WEB.joinpath(name).read_text("utf-8")
    html = re.sub(
        r'\b(href|src)="(\.{1,2}/[^"]+)"',
        lambda match: f'{match[1]}="{urljoin("/" + name, match[2])}"',
        html,
    )
    html = html.replace("__SESSION_TOKEN__", token).replace("__API_BASE__", api)
    return HTTPResponse(html, content_type="text/html; charset=utf-8")


def png(image_bytes: bytes) -> HTTPResponse:
    """``image_bytes`` as a PNG response."""
    return HTTPResponse(image_bytes, content_type="image/png")


def guard(app: Bottle, session: Session) -> None:
    """Add hooks that enforce Host, Origin and the ``/api/`` token and set security headers."""
    host = urlsplit(session.origin).netloc
    token = session.token.encode("utf-8")

    def check_request() -> None:
        # Raw WSGI values, compared before Bottle decodes them as UTF-8.
        if request.environ.get("HTTP_HOST") != host:
            fail(403, "Unexpected Host")
        if request.environ.get("HTTP_ORIGIN") not in {None, session.origin}:
            fail(403, "Cross-origin requests are forbidden")
        sent = request.environ.get("HTTP_X_JAMSHOOT_TOKEN", "").encode("utf-8")
        if request.path.startswith("/api/") and not hmac.compare_digest(sent, token):
            fail(403, "Missing or invalid session token")

    def set_security_headers() -> None:
        response.set_header("Cache-Control", "no-store")
        response.set_header("X-Content-Type-Options", "nosniff")
        response.set_header("Referrer-Policy", "no-referrer")
        response.set_header("Content-Security-Policy", CONTENT_SECURITY_POLICY)

    def unavailable(error: HTTPResponse) -> HTTPResponse:
        message = {"error": {"code": "http_error", "message": "Request unavailable"}}
        return json_response(message, error.status_code)

    app.add_hook("before_request", check_request)
    app.add_hook("after_request", set_security_headers)
    for status in (404, 405, 500):
        app.error(status)(unavailable)
