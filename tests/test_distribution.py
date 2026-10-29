"""License declarations and license text in the wheel and source distribution."""

import io
import tarfile
import unittest
import zipfile

from check_distribution import LICENSE, check_source_license, check_wheel_license


class DistributionLicenseTests(unittest.TestCase):
    """Reject release archives with missing, changed or misdeclared licenses."""

    def test_wheel_requires_the_expression_and_unchanged_license(self):
        """Only Apache-2.0 metadata plus the unchanged LICENSE passes."""
        for expression, content in (
            ("Apache-2.0", LICENSE.read_bytes()),
            ("MIT", LICENSE.read_bytes()),
            ("Apache-2.0", b"changed"),
            ("Apache-2.0", None),
        ):
            with self.subTest(expression=expression, content=content is not None):
                buffer = io.BytesIO()
                with zipfile.ZipFile(buffer, "w") as archive:
                    archive.writestr(
                        "jamshoot_screen_gen-0.1.0.dist-info/METADATA",
                        f"Metadata-Version: 2.4\nLicense-Expression: {expression}\n",
                    )
                    if content is not None:
                        archive.writestr(
                            "jamshoot_screen_gen-0.1.0.dist-info/licenses/LICENSE", content
                        )
                    if expression == "Apache-2.0" and content == LICENSE.read_bytes():
                        check_wheel_license(archive)
                    else:
                        with self.assertRaises(SystemExit):
                            check_wheel_license(archive)

    def test_source_requires_the_unchanged_root_license(self):
        """Only the unchanged root LICENSE passes; a changed or nested one exits."""
        for name, content in (
            ("LICENSE", LICENSE.read_bytes()),
            ("LICENSE", b"changed"),
            ("src/vendor/LICENSE", LICENSE.read_bytes()),
        ):
            with self.subTest(name=name, valid=content == LICENSE.read_bytes()):
                buffer = io.BytesIO()
                with tarfile.open(fileobj=buffer, mode="w") as archive:
                    member = tarfile.TarInfo(f"jamshoot_screen_gen-0.1.0/{name}")
                    member.size = len(content)
                    archive.addfile(member, io.BytesIO(content))
                buffer.seek(0)
                with tarfile.open(fileobj=buffer) as archive:
                    if name == "LICENSE" and content == LICENSE.read_bytes():
                        check_source_license(archive)
                    else:
                        with self.assertRaises(SystemExit):
                            check_source_license(archive)


if __name__ == "__main__":
    unittest.main()
