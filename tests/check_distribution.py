"""Check that release archives contain the whole package and nothing else.

Run after `python -m build`: python tests/check_distribution.py dist
"""

import argparse
import tarfile
import zipfile
from email.parser import BytesParser
from pathlib import Path

PACKAGE = Path(__file__).resolve().parents[1] / "src" / "jamshoot"
FONT_SUFFIXES = {".ttf", ".otf", ".woff", ".woff2"}
EXCLUDED_PARTS = {"node_modules", "__pycache__", ".venv", ".git"}
PRIVATE_PARTS = {".aws", ".ssh", ".codex", ".agents", ".DS_Store", "incoming", "trash"}
DEMO_FILES = {
    "projects/demo/project.json",
    "projects/demo/project.schema.json",
    "projects/demo/assets/screenshot.png",
}
LICENSE = PACKAGE.parents[1] / "LICENSE"


def package_files() -> list[str]:
    """Every source file of the package, relative to ``src``, without caches."""
    return sorted(
        path.relative_to(PACKAGE.parent).as_posix()
        for path in PACKAGE.rglob("*")
        if path.is_file() and "__pycache__" not in path.parts
    )


def _check_archive(kind: str, members: set[str], prefix: str) -> None:
    """Exit if the archive lacks a package file or holds a forbidden one."""
    missing = [name for name in package_files() if prefix + name not in members]
    if missing:
        raise SystemExit(f"{kind} is missing {', '.join(missing)}")
    for member in members:
        path = Path(member)
        if (
            PRIVATE_PARTS & set(path.parts)
            or any(part == ".env" or part.startswith(".env.") for part in path.parts)
            or path.suffix.lower() in {".pem", ".key", ".p12", ".pfx"}
            or ("projects" in path.parts and member not in DEMO_FILES)
        ):
            raise SystemExit(f"Private file in {kind}: {member}")
        if Path(member).suffix.lower() in FONT_SUFFIXES:
            raise SystemExit(f"Font must remain external to {kind}: {member}")
        if EXCLUDED_PARTS & set(Path(member).parts):
            raise SystemExit(f"Unexpected file in {kind}: {member}")


def check_wheel_license(archive: zipfile.ZipFile) -> None:
    """Exit unless the wheel declares Apache-2.0 and ships the unchanged LICENSE."""
    metadata_files = [name for name in archive.namelist() if name.endswith(".dist-info/METADATA")]
    if len(metadata_files) != 1:
        raise SystemExit("Wheel must contain exactly one package metadata file.")
    metadata = BytesParser().parsebytes(archive.read(metadata_files[0]))
    if metadata.get("License-Expression") != "Apache-2.0":
        raise SystemExit("Wheel must declare License-Expression: Apache-2.0.")
    license_path = metadata_files[0].removesuffix("METADATA") + "licenses/LICENSE"
    if license_path not in archive.namelist() or archive.read(license_path) != LICENSE.read_bytes():
        raise SystemExit("Wheel must include the unchanged Apache-2.0 LICENSE.")


def check_source_license(archive: tarfile.TarFile) -> None:
    """Exit unless the source archive has the unchanged LICENSE at its root."""
    names = [
        name for name in archive.getnames() if name.count("/") == 1 and name.endswith("/LICENSE")
    ]
    if len(names) != 1:
        raise SystemExit("Source archive must include one root LICENSE.")
    content = archive.extractfile(names[0])
    if content is None or content.read() != LICENSE.read_bytes():
        raise SystemExit("Source archive must include the unchanged Apache-2.0 LICENSE.")


def check(directory: Path) -> None:
    """Check the single wheel and source distribution in ``directory``; exit on failure."""
    wheels, sdists = list(directory.glob("*.whl")), list(directory.glob("*.tar.gz"))
    if len(wheels) != 1 or len(sdists) != 1:
        raise SystemExit("Expected exactly one wheel and one source distribution.")
    with zipfile.ZipFile(wheels[0]) as archive:
        wheel_files = set(archive.namelist())
        check_wheel_license(archive)
    with tarfile.open(sdists[0]) as archive:
        source_files = {name.partition("/")[2] for name in archive.getnames()}
        check_source_license(archive)
    _check_archive("wheel", wheel_files, "")
    _check_archive("sdist", source_files, "src/")
    if any(not name.startswith(("jamshoot/", "jamshoot_studio-")) for name in wheel_files):
        raise SystemExit("Wheel contains files outside the application package and metadata.")
    print("Wheel and sdist contain every package file and Apache-2.0 license; no fonts or tools.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    check(parser.parse_args().directory)
