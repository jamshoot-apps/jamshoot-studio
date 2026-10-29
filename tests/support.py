"""Shared test fixtures: temporary folders, an in-process WSGI client and the CLI."""

import atexit
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from collections.abc import Callable, Iterable
from pathlib import Path
from typing import Any, NamedTuple
from wsgiref.util import setup_testing_defaults

from jamshoot.core.appearance import STARTER_PALETTES
from jamshoot.fonts import default_families
from jamshoot.typefaces import system_faces

ROOT = Path(__file__).resolve().parents[1]
# Studio settings written by tests land here, never in the user's own file.
SETTINGS_FOLDER = Path(tempfile.mkdtemp(prefix="jamshoot-settings-"))
atexit.register(shutil.rmtree, SETTINGS_FOLDER, ignore_errors=True)
os.environ["JAMSHOOT_SETTINGS"] = str(SETTINGS_FOLDER / "settings.json")
os.environ.pop("JAMSHOOT_HOME", None)

HOST = "127.0.0.1:8765"
ORIGIN = f"http://{HOST}"
# A complete palette unlike any starter: Midnight's text colors with custom stops.
BRAND_COLORS = STARTER_PALETTES["midnight"] | {
    "top": "#123456",
    "bottom": "#abcdef",
    "accent": "#cc5588",
}
# Request keywords of ``WsgiClient.request`` and the WSGI environ keys they set.
ENVIRON = {
    "host": "HTTP_HOST",
    "origin": "HTTP_ORIGIN",
    "token": "HTTP_X_JAMSHOOT_TOKEN",
    "content_type": "CONTENT_TYPE",
}


def installed_font() -> Path:
    """Path of an installed regular TTF or OTF font, preferring a default family.

    Skips the calling test when none is installed. Tests use it so the repository needs no font.
    """
    candidates = [
        face
        for face in system_faces()
        if face.weight == 400
        and not face.italic
        and Path(face.path).suffix.lower() in {".ttf", ".otf"}
    ]
    preferred = [face for face in candidates if face.family in default_families()]
    if not preferred + candidates:
        raise unittest.SkipTest("No regular TTF or OTF font is installed")
    return Path((preferred + candidates)[0].path)


def temporary_directory(test: unittest.TestCase, prefix: str | None = None) -> Path:
    """A resolved temporary folder that is removed when ``test`` finishes."""
    path = Path(tempfile.mkdtemp(prefix=prefix)).resolve()
    test.addCleanup(shutil.rmtree, path, ignore_errors=True)
    return path


def run_jamshoot(*args: object, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    """Run ``python -m jamshoot`` with ``args``; the caller checks the exit code."""
    return subprocess.run(
        [sys.executable, "-m", "jamshoot", *map(str, args)],
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )


def _encode(body: Any) -> bytes:
    if body is None:
        return b""
    return body if isinstance(body, bytes) else json.dumps(body).encode()


def _environ(
    method: str, target: str, content: bytes, headers: dict[str, str | None]
) -> dict[str, Any]:
    """The WSGI environ for one request; ``None`` headers are omitted."""
    path, _, query = target.partition("?")
    environ: dict[str, Any] = {}
    setup_testing_defaults(environ)
    environ.update(
        {
            "REQUEST_METHOD": method,
            "PATH_INFO": path,
            "QUERY_STRING": query,
            "CONTENT_LENGTH": str(len(content)),
            "wsgi.input": io.BytesIO(content),
        }
    )
    defaults: dict[str, str | None] = {"host": HOST, "content_type": "application/json"}
    for name, value in (defaults | headers).items():
        if value is not None:
            environ[ENVIRON[name]] = value
    return environ


class Response(NamedTuple):
    """A captured WSGI response."""

    status: int
    headers: dict[str, str]
    body: bytes

    def json(self) -> Any:
        """The body parsed as JSON."""
        return json.loads(self.body)


class WsgiClient:
    """Calls a WSGI app in-process as the Studio front end would, with its token."""

    def __init__(self, app: Callable[..., Iterable[bytes]], token: str):
        self.app, self.token = app, token

    def request(
        self, path: str, method: str = "GET", body: Any = None, **headers: str | None
    ) -> Response:
        """Send one request.

        ``body``: bytes as is, ``None`` empty, else JSON. ``host``, ``origin``, ``token`` and
        ``content_type`` override the defaults; ``None`` omits the header.
        """
        session: dict[str, str | None] = {"token": self.token}
        environ = _environ(method, path, _encode(body), session | headers)
        captured: list[tuple[str, dict[str, str]]] = []
        result = self.app(environ, lambda status, items, *_: captured.append((status, dict(items))))
        try:
            data = b"".join(result)
        finally:
            close = getattr(result, "close", None)
            if close is not None:
                close()
        status, response_headers = captured[0]
        return Response(int(status[:3]), response_headers, data)

    def json(self, path: str, method: str = "GET", body: Any = None, **headers: str | None):
        """Status and parsed JSON body of one request."""
        response = self.request(path, method, body, **headers)
        return response.status, response.json()
