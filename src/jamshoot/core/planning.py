"""Expand a project into its ordered render jobs, without rendering or writing files."""

from collections.abc import Callable, Iterator
from functools import cache
from itertools import product
from pathlib import Path, PurePosixPath
from typing import Any

from jamshoot.catalog import find_target
from jamshoot.core.appearance import auto_layout, resolve_text
from jamshoot.core.project import Project, ProjectError, effective_style, slide_asset, variants
from jamshoot.typefaces import Face, find_face

# Finds the face for a family and weight; one plan looks each pair up once.
FaceFinder = Callable[[str, float], Face]


def _fonts(find: FaceFinder, job: dict[str, Any]) -> dict[str, list[Any]]:
    """Each text field of ``job`` that sets a font, mapped to ``[path, face index]``."""
    return {
        field: [face.path, face.number]
        for field, text in resolve_text(job).items()
        if text["font"]
        for face in [find(text["font"], text["weight"])]
    }


def _with_fonts(project: Project, jobs: Iterator[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """The jobs, each with a ``fonts`` map when a text field sets a font family."""
    project_dir: Path = project.path.parent
    find: FaceFinder = cache(lambda family, weight: find_face(project_dir, family, weight))
    for job in jobs:
        if fonts := _fonts(find, job):
            job["fonts"] = fonts
        yield job


def _jobs(project: Project) -> Iterator[dict[str, Any]]:
    """The render jobs, one per variant, locale, target and slide, in output order."""
    data = project.data
    locales: list[str] = data["locales"]
    target_ids: list[str] = data["targets"]
    for variant, locale, target_id in product(variants(data), locales, target_ids):
        target = find_target(target_id)
        if target is None:
            raise ProjectError(f"targets: unknown target {target_id}")
        for index, slide in enumerate(data["slides"], 1):
            style = effective_style(data, slide, variant)
            source = slide_asset(project, slide, target["platform"], locale)
            if style["layout"] == "auto":
                style["layout"] = auto_layout(target)
            filename = f"{index:02d}-{slide['id']}.png"
            yield {
                "slide": slide["id"],
                "variant": variant["id"],
                "locale": locale,
                "target": target_id,
                "width": target["width"],
                "height": target["height"],
                "platform": target["platform"],
                "hardware": target["hardware"],
                "output": str(PurePosixPath(variant["id"], locale, target_id, filename)),
                # None until the slide has this platform's screenshot; previews show a blank screen.
                "source": None if source is None else str(source),
                **slide["copy"][locale],
                **style,
            }


def plan_project(project: Project, *, max_files: int = 1000) -> dict[str, Any]:
    """The plan for ``project``, one job per output file; ProjectError above ``max_files``."""
    data = project.data
    count = len(variants(data)) * len(data["locales"]) * len(data["targets"]) * len(data["slides"])
    if max_files < 1 or count > max_files:
        raise ProjectError(f"Plan contains {count} files; limit is {max_files}")
    return {"version": 1, "fileCount": count, "files": list(_with_fonts(project, _jobs(project)))}
