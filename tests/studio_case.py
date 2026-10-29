"""Studio served in-process over WSGI for the HTTP contract tests."""

import unittest
from html.parser import HTMLParser
from typing import Any

from jamshoot.core.starter import init_project
from jamshoot.library import ProjectLibrary
from jamshoot.server import Session, create_app
from support import ORIGIN, WsgiClient, temporary_directory

TOKEN = "test-session-token"
VOID_ELEMENTS = {"input", "img", "meta", "link", "br", "hr"}


class PageElements(HTMLParser):
    """Tag, attributes and ancestor ids of each element with an id."""

    def __init__(self) -> None:
        super().__init__()
        self.stack: list[tuple[str, str | None]] = []
        self.elements: dict[str, tuple[str, dict[str, Any], list[str | None]]] = {}

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if "id" in attributes:
            ancestors = [element_id for _, element_id in self.stack]
            self.elements[str(attributes["id"])] = (tag, attributes, ancestors)
        if tag not in VOID_ELEMENTS:
            self.stack.append((tag, attributes.get("id")))

    def handle_endtag(self, tag: str) -> None:
        for index in range(len(self.stack) - 1, -1, -1):
            if self.stack[index][0] == tag:
                del self.stack[index:]
                break


class StudioCase(unittest.TestCase):
    """Studio with one fresh starter project in its library."""

    def setUp(self):
        self.root = temporary_directory(self)
        self.path = init_project(self.root / "project")
        library = ProjectLibrary(self.root / "home")
        project_id = library.open_in_place(self.path, self.root / "output")["id"]
        self.editor = f"/project/{project_id}"
        self.api = f"/api/projects/{project_id}"
        self.client = WsgiClient(create_app(library, Session(TOKEN, ORIGIN)), TOKEN)

    def page(self) -> PageElements:
        """The editor page's elements by id."""
        parser = PageElements()
        parser.feed(self.client.request(self.editor).body.decode())
        return parser

    def preview(self, project: dict[str, Any], index: int = 0) -> bytes:
        """PNG bytes of planned file ``index`` of the unsaved ``project``."""
        body = {"project": project, "index": index}
        response = self.client.request(f"{self.api}/preview", "POST", body)
        self.assertEqual(response.status, 200)
        return response.body

    def exported(self, project: dict[str, Any]) -> list[bytes]:
        """Export ``project`` and return the bytes of every file it wrote."""
        status, manifest = self.client.json(f"{self.api}/export", "POST", {"project": project})
        self.assertEqual(status, 200)
        output = self.root / "output"
        return [(output / item["output"]).read_bytes() for item in manifest["files"]]
