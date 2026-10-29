"""Sequential batch export with checksums and all-or-nothing directory publication."""

import hashlib
import io
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any

from PIL import Image

from jamshoot import __version__
from jamshoot.catalog import load_catalog
from jamshoot.core.planning import plan_project
from jamshoot.core.project import Project, ProjectError, require_screenshots
from jamshoot.render.compositor import render_job


def png_bytes(image: Image.Image) -> bytes:
    """Encode ``image`` as PNG with the compression every export uses."""
    stream = io.BytesIO()
    image.save(stream, format="PNG", compress_level=6)
    return stream.getvalue()


def render_project(
    project: Project, output: str | Path, *, max_files: int = 1000
) -> dict[str, Any]:
    """Render every planned file into the new directory ``output``; return the manifest."""
    require_screenshots(project)
    plan = plan_project(project, max_files=max_files)
    output = Path(output).absolute()
    staging = None
    reserved = False
    try:
        if output.exists() or output.is_symlink():
            raise ProjectError(f"Output already exists: {output}; choose a new directory")
        if not output.parent.is_dir():
            raise ProjectError(f"Output parent directory does not exist: {output.parent}")
        staging = Path(tempfile.mkdtemp(prefix=".jamshoot-", dir=output.parent))
        manifest = {
            "version": 1,
            "rendererVersion": __version__,
            "catalogVersion": load_catalog()["version"],
            "fileCount": plan["fileCount"],
            "files": [],
        }
        for job in plan["files"]:
            with render_job(job) as image:
                content = png_bytes(image)
            destination = staging / job["output"]
            destination.parent.mkdir(parents=True, exist_ok=True)
            destination.write_bytes(content)
            manifest["files"].append(
                {
                    key: job[key]
                    for key in ("slide", "variant", "locale", "target", "width", "height", "output")
                }
                | {"sha256": hashlib.sha256(content).hexdigest()}
            )
        (staging / "manifest.json").write_text(
            json.dumps(manifest, indent=2) + "\n", encoding="utf-8"
        )
        # Reserve exclusively on every OS. Only fully rendered files are published.
        output.mkdir()
        reserved = True
        for child in staging.iterdir():
            child.replace(output / child.name)
        staging.rmdir()
        staging = None
        return manifest
    except OSError as error:
        raise ProjectError(f"Cannot export images: {error}") from error
    finally:
        if staging is not None:
            shutil.rmtree(staging)
            if reserved:
                shutil.rmtree(output)
