"""Studio project library: project folders, start screen and per-project editor API."""

import io
import json
import unittest
import zipfile
from pathlib import Path
from unittest.mock import patch

from PIL import Image

from jamshoot.cli import main
from jamshoot.core.planning import plan_project
from jamshoot.core.project import ProjectError, load_project
from jamshoot.core.starter import init_project
from jamshoot.library import ProjectLibrary
from jamshoot.server import Session, create_app
from support import ORIGIN, WsgiClient, temporary_directory


class LibraryTests(unittest.TestCase):
    """Studio's project folders, start screen API and per-project editor routes."""

    def setUp(self):
        self.root = temporary_directory(self)
        self.library = ProjectLibrary(self.root / "home")
        self.client = WsgiClient(
            create_app(self.library, Session("library-token", ORIGIN)), "library-token"
        )

    def test_studio_starters_wait_for_a_real_screenshot_while_the_cli_example_renders(self):
        """Platform starters have no screenshot; the CLI example ships a sample one."""
        for platform in ("iphone", "ipad", "mac"):
            with self.subTest(platform=platform):
                path = init_project(self.root / platform, name=f"{platform} app", platform=platform)
                project = load_project(path)
                job = plan_project(project)["files"][0]
                self.assertEqual((job["platform"], job["source"]), (platform, None))
                self.assertEqual(project.data["slides"][0]["name"], "Slide 1")
                self.assertEqual(list((path.parent / "assets").iterdir()), [])
        example = init_project(self.root / "example")
        with Image.open(example.parent / "assets/screenshot.png") as image:
            self.assertEqual(image.size, (1440, 900))
        with self.assertRaisesRegex(ProjectError, "platform"):
            init_project(self.root / "tv", platform="tv")

    def test_start_screen_creates_lists_opens_and_trashes_projects(self):
        """New projects list, open, serve a cached thumbnail and move to the trash."""
        status, headers, html = self.client.request("/", token=None)
        self.assertEqual(status, 200)
        self.assertIn("New project", html.decode())
        self.assertIn("library-token", html.decode())
        status, created = self.client.json(
            "/api/projects", "POST", {"name": "Café App", "platform": "iphone"}
        )
        self.assertEqual(status, 201)
        self.assertEqual(
            (created["name"], created["platforms"], created["slides"]), ("Café App", ["iphone"], 1)
        )
        self.assertTrue(created["managed"])
        project_id = created["id"]
        status, listing = self.client.json("/api/projects")
        self.assertEqual([item["id"] for item in listing["projects"]], [project_id])
        status, _, page = self.client.request(f"/project/{project_id}", token=None)
        self.assertEqual(status, 200)
        self.assertIn(f'content="/api/projects/{project_id}"', page.decode())
        status, snapshot = self.client.json(f"/api/projects/{project_id}/project")
        self.assertEqual(status, 200)
        self.assertEqual(snapshot["project"]["project"]["name"], "Café App")
        status, headers, thumbnail = self.client.request(f"/api/projects/{project_id}/thumbnail")
        self.assertEqual(status, 200)
        self.assertIn("image/png", headers["Content-Type"])
        with Image.open(io.BytesIO(thumbnail)) as image:
            self.assertLessEqual(image.width, 480)
        # A second request is served from the cache for the same revision.
        self.assertEqual(self.library.thumbnails[project_id][1], thumbnail)
        self.assertEqual(self.client.request(f"/api/projects/{project_id}/thumbnail")[2], thumbnail)
        folder = self.root / "home/projects" / project_id
        self.assertEqual(self.library.path(project_id), folder / "project.json")
        status, removed = self.client.json(f"/api/projects/{project_id}", "DELETE")
        self.assertEqual(status, 200)
        self.assertTrue((Path(removed["movedTo"]) / "project.json").is_file())
        self.assertFalse(folder.exists())
        self.assertEqual(self.client.json("/api/projects")[1]["projects"], [])
        self.assertEqual(self.client.request(f"/project/{project_id}", token=None)[0], 404)
        self.assertEqual(self.client.request(f"/api/projects/{project_id}/project")[0], 404)
        self.assertEqual(self.client.request("/api/projects/../project")[0], 404)

    def test_copied_folders_are_projects(self):
        """Any folder in ``projects/`` with a ``project.json`` is listed."""
        init_project(self.root / "home/projects/demo", name="Demo", platform="iphone")
        (self.root / "home/projects/notes").mkdir()
        listing = self.client.json("/api/projects")[1]["projects"]
        self.assertEqual([(item["id"], item["name"]) for item in listing], [("demo", "Demo")])
        self.assertEqual(
            self.library.output("demo"), self.root / "home/projects/demo/exports/export"
        )

    def import_zip(self, content: bytes):
        """POST a .zip to the import endpoint; returns (status, JSON body)."""
        response = self.client.request(
            "/api/projects/import", "POST", content, content_type="application/zip"
        )
        return response.status, response.json()

    def test_zip_export_and_import_round_trip_into_a_new_folder(self):
        """A .zip export holds only project files and imports as a separate, editable project."""
        created = self.library.create("Café App", "iphone")
        source = Path(created["path"])
        Image.new("RGB", (1179, 2556), "white").save(source.parent / "assets/home.png")
        data = json.loads(source.read_text("utf-8"))
        data["slides"][0]["assets"] = {"iphone": "./assets/home.png"}
        source.write_text(json.dumps(data), encoding="utf-8")
        (source.parent / "exports").mkdir()
        (source.parent / "exports/old.png").write_bytes(b"not exported")
        (source.parent / "notes.txt").write_text("not exported", encoding="utf-8")
        status, headers, content = self.client.request(f"/api/projects/{created['id']}/archive")
        self.assertEqual(status, 200)
        self.assertEqual(headers["Content-Type"], "application/zip")
        self.assertIn('filename="caf-app.zip"', headers["Content-Disposition"])
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            self.assertEqual(
                sorted(archive.namelist()),
                [
                    "caf-app/assets/home.png",
                    "caf-app/project.json",
                    "caf-app/project.schema.json",
                ],
            )
        status, item = self.import_zip(content)
        self.assertEqual(status, 201)
        self.assertNotEqual(item["id"], created["id"])
        self.assertTrue(item["managed"])
        self.assertEqual((item["name"], item["platforms"]), ("Café App", ["iphone"]))
        path = Path(item["path"])
        self.assertEqual(path.parent.parent, self.root / "home/projects")
        self.assertTrue((path.parent / "assets/home.png").is_file())
        self.assertEqual(list(self.library.folder.glob(".import-*")), [])
        base = f"/api/projects/{item['id']}"
        _, snapshot = self.client.json(base + "/project")
        snapshot["project"]["project"]["name"] = "Renamed"
        status, saved = self.client.json(
            base + "/project",
            "POST",
            {"project": snapshot["project"], "revision": snapshot["revision"]},
        )
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(path.read_text("utf-8"))["project"]["name"], "Renamed")
        self.assertEqual(json.loads(source.read_text("utf-8"))["project"]["name"], "Café App")
        status, manifest = self.client.json(base + "/export", "POST", {"project": saved["project"]})
        self.assertEqual(status, 200)
        self.assertEqual(manifest["outputDirectory"], str(path.parent / "exports" / "export"))

    def test_zip_import_accepts_a_flat_finder_archive(self):
        """project.json may sit at the top level; Finder's metadata entries are skipped."""
        source = init_project(self.root / "flat", name="Flat")
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for item in ("project.json", "assets/screenshot.png"):
                archive.write(source.parent / item, item)
            archive.writestr("__MACOSX/._project.json", b"resource fork")
            archive.writestr(".DS_Store", b"finder")
        status, item = self.import_zip(buffer.getvalue())
        self.assertEqual((status, item["name"]), (201, "Flat"))
        folder = Path(item["path"]).parent
        self.assertEqual(
            sorted(p.relative_to(folder).as_posix() for p in folder.rglob("*") if p.is_file()),
            ["assets/screenshot.png", "project.json"],
        )

    def test_zip_import_rejects_unsafe_or_invalid_archives_and_leaves_nothing(self):
        """Invalid archives return 400 and leave no folder behind."""
        project = init_project(self.root / "valid").read_bytes()
        cases = {
            "not a zip": (b"plain text", "Expected a project .zip"),
            "no project": (self.zip_of({"readme.txt": b"hi"}), "project.json"),
            "escape": (
                self.zip_of({"project.json": project, "../evil.png": b"x"}),
                "Unsafe path",
            ),
            "missing image": (self.zip_of({"project.json": project}), "assets/screenshot.png"),
        }
        for label, (content, message) in cases.items():
            with self.subTest(label):
                status, error = self.import_zip(content)
                self.assertEqual(status, 400)
                self.assertIn(message, error["error"]["message"])
                self.assertEqual(list(self.library.folder.iterdir()), [])

    @staticmethod
    def zip_of(entries: dict[str, bytes]) -> bytes:
        """A .zip holding ``entries`` (name to bytes)."""
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w") as archive:
            for name, data in entries.items():
                archive.writestr(name, data)
        return buffer.getvalue()

    def test_projects_opened_in_place_are_forgotten_not_moved(self):
        """A project opened in place lists first, keeps its export folder and is never moved."""
        self.library.create("Other", "mac")
        path = init_project(self.root / "existing")
        item = self.library.open_in_place(path, self.root / "out")
        self.assertFalse(item["managed"])
        self.assertEqual(self.library.open_in_place(path)["id"], item["id"])
        self.assertEqual(self.library.output(item["id"]), self.root / "out")
        self.assertEqual(self.client.json("/api/projects")[1]["projects"][0]["id"], item["id"])
        removed = self.client.json(f"/api/projects/{item['id']}", "DELETE")[1]
        self.assertIsNone(removed["movedTo"])
        self.assertTrue(path.is_file())

    def test_studio_command_passes_home_and_open_to_the_server(self):
        """``jamshoot studio --home DIR --open`` starts the library at DIR in the browser."""
        with patch("jamshoot.cli.STUDIO") as serve:
            self.assertEqual(main(["studio", "--home", str(self.root), "--open"]), 0)
        serve.assert_called_once_with(
            None, homes=(self.root, None), port=8765, max_files=1000, open_browser=True
        )

    def test_library_rejects_bad_input_and_requires_the_session_token(self):
        """A missing token is 403, bad input 400; an unreadable project still lists."""
        self.assertEqual(self.client.request("/api/projects", token=None)[0], 403)
        for payload in ({"name": " ", "platform": "iphone"}, {"name": "A", "platform": "watch"}):
            self.assertEqual(self.client.json("/api/projects", "POST", payload)[0], 400)
        self.assertEqual(self.client.request("/api/projects/none/archive")[0], 404)
        item = self.library.create("Broken", "mac")
        Path(item["path"]).write_text("{", encoding="utf-8")
        listed = self.client.json("/api/projects")[1]["projects"][0]
        self.assertEqual(listed["id"], item["id"])
        self.assertIn("unavailable", listed["error"])


if __name__ == "__main__":
    unittest.main()
