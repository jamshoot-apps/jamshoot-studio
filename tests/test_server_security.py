"""Studio request guards: token, origin, host, traversal, timeouts and limits."""

import io
import socket
import unittest
from contextlib import closing
from http.client import HTTPConnection
from threading import Thread
from unittest.mock import patch
from wsgiref.simple_server import make_server

from PIL import Image

from jamshoot.server import RequestHandler
from studio_case import StudioCase
from support import HOST


class StudioSecurityTests(StudioCase):
    """Token, origin and host checks plus strict request validation."""

    def test_stalled_requests_time_out_and_the_server_accepts_the_next_request(self):
        """Stalled request lines, headers and bodies time out; the next request still works."""
        partial_requests = (
            b"GET / HT",
            b"GET / HTTP/1.1\r\nHost: " + HOST.encode(),
            (
                f"POST {self.api}/plan HTTP/1.1\r\nHost: {HOST}\r\n"
                f"X-JamShoot-Token: {self.client.token}\r\n"
                "Content-Type: application/json\r\nContent-Length: 100\r\n\r\n{"
            ).encode(),
        )
        with (
            patch.object(RequestHandler, "timeout", 0.1),
            make_server("127.0.0.1", 0, self.client.app, handler_class=RequestHandler) as server,
        ):
            address = ("127.0.0.1", server.server_port)
            worker = Thread(target=server.serve_forever, daemon=True)
            worker.start()
            try:
                for partial in partial_requests:
                    with (
                        self.subTest(partial=partial),
                        socket.create_connection(address, timeout=2) as stalled,
                        closing(HTTPConnection(*address, timeout=2)) as client,
                    ):
                        stalled.sendall(partial)
                        client.request("GET", "/", headers={"Host": HOST})
                        response = client.getresponse()
                        self.assertEqual(response.status, 200)
                        response.read()
                        # Drain any error response and prove the stalled socket was closed.
                        while stalled.recv(4096):
                            pass
            finally:
                server.shutdown()
                worker.join(timeout=2)
            self.assertFalse(worker.is_alive())

    def test_missing_token_cross_origin_rebinding_traversal_and_invalid_requests_fail(self):
        """No token, a foreign origin or host gets 403; traversal gets 404, bad bodies 400."""
        project = f"{self.api}/project"
        forbidden = {
            "no token": self.client.request(project, token=None),
            "cross origin": self.client.request(project, origin="https://evil.example"),
            "rebinding": self.client.request(project, host="evil.example:8765"),
        }
        for case, response in forbidden.items():
            with self.subTest(case=case):
                self.assertEqual(response.status, 403)
        self.assertEqual(self.client.request("/../pyproject.toml").status, 404)
        for path, data in (
            (f"{self.api}/plan", {"project": {}}),
            (f"{self.api}/preview", {"project": {}, "index": -1}),
            (f"{self.api}/project", b'{"project":NaN}'),
        ):
            status, result = self.client.json(path, "POST", data)
            self.assertEqual(status, 400)
            self.assertIn("error", result)
        self.assertFalse((self.root / "output").exists())

    def test_invalid_non_ascii_token_returns_forbidden_instead_of_server_error(self):
        """A non-ASCII token gets 403, not a server error."""
        self.assertEqual(self.client.json(f"{self.api}/project", token="неверный")[0], 403)

    def test_preview_rejects_non_integer_and_out_of_range_indices(self):
        """Preview indices that are not in-range integers get 400."""
        _, initial = self.client.json(f"{self.api}/project")
        for index in (-1, 1, True, "0", None):
            with self.subTest(index=index):
                body = {"project": initial["project"], "index": index}
                self.assertEqual(self.client.json(f"{self.api}/preview", "POST", body)[0], 400)

    def test_api_rejects_duplicate_keys_wrong_type_and_oversized_bodies(self):
        """Malformed JSON is 400, other media types 415 and bodies over 1 MiB 413."""
        for body in (b'{"project":{},"project":{}}', b"[]", b"{bad"):
            self.assertEqual(self.client.json(f"{self.api}/plan", "POST", body)[0], 400)
        plain = self.client.json(f"{self.api}/plan", "POST", b"{}", content_type="text/plain")
        self.assertEqual(plain[0], 415)
        self.assertEqual(self.client.json(f"{self.api}/plan", "POST", b" " * 1_048_577)[0], 413)

    def test_upload_refuses_a_symlink_directory(self):
        """Uploads fail with 400 when ``assets`` is a symlink."""
        original = self.path.parent / "assets"
        renamed = self.path.parent / "original-assets"
        original.rename(renamed)
        try:
            original.symlink_to(renamed, target_is_directory=True)
        except OSError:
            self.skipTest("Symlinks unavailable on this host")
        image = io.BytesIO()
        Image.new("RGB", (10, 10)).save(image, "PNG")
        self.assertEqual(self.client.json(f"{self.api}/assets", "POST", image.getvalue())[0], 400)


if __name__ == "__main__":
    unittest.main()
