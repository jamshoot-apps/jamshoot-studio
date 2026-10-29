"""Versioned project loading and semantic validation."""

import json
from copy import deepcopy
from dataclasses import dataclass
from importlib.resources import files
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from jsonschema import Draft202012Validator
from jsonschema.exceptions import ValidationError

from jamshoot.catalog import CUSTOM_MAX_PIXELS, find_target
from jamshoot.core.appearance import STYLE_DEFAULTS, layout_allowed

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp"}
WINDOWS_RESERVED_NAMES = {
    "con",
    "prn",
    "aux",
    "nul",
    *(f"com{i}" for i in range(1, 10)),
    *(f"lpt{i}" for i in range(1, 10)),
}
# Saved style libraries: (list in the project, link key in a style, value groups an entry holds).
SAVED_STYLES = (
    ("colorStyles", "colorStyle", ("colors", "gradient")),
    ("layoutStyles", "layoutStyle", ("layoutSettings",)),
)


class ProjectError(ValueError):
    """A project cannot be loaded, validated or safely planned."""

    def __init__(self, message: str, *, issues: list[dict[str, str]] | None = None) -> None:
        super().__init__(message)
        self.issues = issues or []


@dataclass(frozen=True)
class Project:
    """A validated project document and the resolved path it was loaded from."""

    path: Path
    data: dict[str, Any]


def load_schema() -> dict[str, Any]:
    """The bundled project schema."""
    return json.loads(files("jamshoot").joinpath("data", "project.schema.json").read_text("utf-8"))


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ProjectError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def _reject_nonfinite(value: str) -> None:
    raise ProjectError(f"Non-finite JSON number: {value}")


def parse_json(content: str | bytes) -> Any:
    """``content`` as strict JSON; duplicate keys, NaN and Infinity raise ProjectError."""
    return json.loads(
        content, object_pairs_hook=_reject_duplicate_keys, parse_constant=_reject_nonfinite
    )


def variants(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The project's ``variants``, or one ``default`` variant when it has none."""
    return data.get("variants", [{"id": "default"}])


def resolve_asset(project: Project, value: str) -> Path:
    """The resolved path of image ``value``; ProjectError unless it is inside the project."""
    path = PurePosixPath(value)
    if (
        any(mark in value for mark in ("\\", ":", "\x00"))
        or path.is_absolute()
        or PureWindowsPath(value).drive
        or ".." in path.parts
    ):
        raise ProjectError(f"Asset must be a portable relative project path: {value}")
    try:
        resolved = (project.path.parent / path).resolve()
        if not resolved.is_relative_to(project.path.parent) or not resolved.is_file():
            raise ProjectError(f"Missing or external project asset: {value}")
        if resolved.suffix.lower() not in IMAGE_SUFFIXES:
            raise ProjectError(f"Unsupported project image: {value}")
    except (OSError, ValueError, RuntimeError) as error:
        if isinstance(error, ProjectError):
            raise
        raise ProjectError(f"Cannot read project asset {value}: {error}") from error
    return resolved


def slide_asset(project: Project, slide: dict[str, Any], platform: str, locale: str) -> Path | None:
    """The slide's image path for ``platform`` and ``locale``, or None when it has none."""
    value = slide["assets"].get(platform)
    if isinstance(value, dict):
        value = value.get(locale)
    return None if value is None else resolve_asset(project, value)


# How Studio names each platform, so messages match what people see there.
PLATFORM_NAMES = {"mac": "Mac", "iphone": "iPhone", "iphone-duo": "Duo", "ipad": "iPad"}


def missing_screenshots(project: Project) -> list[str]:
    """A message for each slide, platform and locale without a screenshot, in Studio's terms."""
    data = project.data
    platforms = dict.fromkeys(target["platform"] for target in _targets(data))
    languages = len(data["locales"]) > 1
    return [
        f"Slide {number} ({slide['id']}): no {PLATFORM_NAMES.get(platform, platform)} screenshot"
        + (f" for {locale}" if languages else "")
        for number, slide in enumerate(data["slides"], 1)
        for platform in platforms
        for locale in data["locales"]
        if slide_asset(project, slide, platform, locale) is None
    ]


def require_screenshots(project: Project) -> None:
    """Raise ProjectError listing up to five missing screenshots; rendering needs all of them."""
    missing = missing_screenshots(project)
    if missing:
        more = f"\n…and {len(missing) - 5} more" if len(missing) > 5 else ""
        raise ProjectError("Add the missing screenshots first:\n" + "\n".join(missing[:5]) + more)


def effective_style(data: dict, slide: dict, variant: dict) -> dict:
    """The merged style of ``slide`` in ``variant``: project defaults, variant, then slide."""
    layers = [
        data["defaults"],
        {key: value for key, value in variant.items() if key != "id"},
        slide.get("style", {}),
    ]
    style: dict[str, Any] = dict(STYLE_DEFAULTS)
    for layer in layers:
        style.update(layer)
    if any("patternSettings" in layer for layer in layers):
        style["patternSettings"] = {
            key: value
            for layer in layers
            for key, value in layer.get("patternSettings", {}).items()
        }
    # Typography merges per text field, then setting by setting.
    if any("typography" in layer for layer in layers):
        typography: dict[str, dict[str, Any]] = {}
        for layer in layers:
            for field, values in layer.get("typography", {}).items():
                typography.setdefault(field, {}).update(values)
        style["typography"] = typography
    # Linked groups merge key by key too; a link restarts from the saved entry's values.
    for library, link, groups in SAVED_STYLES:
        for values in groups:
            if any(values in layer or link in layer for layer in layers):
                style[values] = _linked_values(data, layers, (library, link, values))
    return style


def _linked_values(
    data: dict[str, Any], layers: list[dict[str, Any]], kind: tuple[str, str, str]
) -> dict[str, Any]:
    """One saved-style group: each link restarts from its saved values; local values override."""
    library, link, values = kind
    saved = {style["id"]: style.get(values, {}) for style in data.get(library, [])}
    result: dict[str, Any] = {}
    for layer in layers:
        if link in layer:
            result = dict(saved.get(layer[link], {}))
        result.update(layer.get(values, {}))
    return result


def load_project(path: str | Path) -> Project:
    """The validated project at ``path``; raises ProjectError if unreadable or invalid."""
    try:
        path = Path(path).resolve()
        data = parse_json(path.read_text(encoding="utf-8"))
    except (OSError, ValueError, RuntimeError) as error:
        raise ProjectError(f"Cannot read project: {error}") from error
    return validate_project(data, path)


def _field_message(error: ValidationError) -> str:
    """A short schema error message that does not echo the invalid value."""
    limit = error.validator_value
    if error.validator == "maxLength":
        return f"Use at most {limit} characters."
    if error.validator == "minLength":
        return f"Enter at least {limit} character(s)."
    if error.validator == "pattern":
        return (
            "Enter text containing at least one non-space character."
            if limit == r"\S"
            else "Use the required format for this field."
        )
    if error.validator == "type":
        return f"Expected {limit}."
    if error.validator in {"minimum", "maximum"}:
        bound = "at least" if error.validator == "minimum" else "at most"
        return f"Use a value {bound} {limit}."
    return error.message[:300]


def validate_project(data: Any, path: str | Path) -> Project:
    """The validated ``Project`` for ``data`` as if saved at ``path``; ``data`` is not changed.

    Raises ProjectError with up to 20 schema ``issues`` if invalid.
    """
    path = Path(path).resolve()
    errors = list(Draft202012Validator(load_schema()).iter_errors(data))
    if errors:
        issues = [
            {
                "path": "/"
                + "/".join(
                    str(part).replace("~", "~0").replace("/", "~1") for part in error.absolute_path
                ),
                "message": _field_message(error),
            }
            for error in errors[:20]
        ]
        messages = [
            f"{'/'.join(map(str, error.absolute_path)) or '/'}: {error.message}"
            for error in errors[:20]
        ]
        raise ProjectError("Invalid project:\n" + "\n".join(messages), issues=issues)
    project = Project(path, deepcopy(data))
    targets = _targets(project.data)
    _check_saved_styles(project.data)
    _check_layouts(project.data, targets)
    _check_unique_ids(project.data["slides"], "slides")
    _check_unique_ids(variants(project.data), "variants")
    _check_unique_ids([{"id": locale.lower()} for locale in project.data["locales"]], "locales")
    _check_text_and_assets(project)
    return project


def _check_unique_ids(items: list[dict[str, Any]], section: str) -> None:
    seen = set()
    for item in items:
        name = item["id"]
        if name in seen or name.split(".", 1)[0].rstrip(" ").lower() in WINDOWS_RESERVED_NAMES:
            raise ProjectError(f"{section}/id: duplicate or nonportable id {name}")
        seen.add(name)


def _targets(data: dict[str, Any]) -> list[dict[str, Any]]:
    """The catalog entry or custom size of each project target; ProjectError if unknown."""
    found = []
    for target_id in data["targets"]:
        target = find_target(target_id)
        if target is None:
            raise ProjectError(
                f"targets: unknown target {target_id}; choose a catalog size or custom.<w>x<h>"
                f" with sides from 64 to 8192 and at most {CUSTOM_MAX_PIXELS:,} pixels"
            )
        found.append(target)
    return found


def _check_saved_styles(data: dict[str, Any]) -> None:
    """Check that saved style ids are unique and every link points to one of them."""
    scopes = [("defaults", data["defaults"])]
    scopes += [(f"variants/{i}", variant) for i, variant in enumerate(data.get("variants", []))]
    scopes += [
        (f"slides/{i}/style", slide.get("style", {})) for i, slide in enumerate(data["slides"])
    ]
    for library, link, _ in SAVED_STYLES:
        styles = data.get(library, [])
        _check_unique_ids(styles, library)
        known = {style["id"] for style in styles}
        for scope, style in scopes:
            reference = style.get(link)
            if reference is not None and reference not in known:
                noun = "palette" if link == "colorStyle" else "layout template"
                raise ProjectError(f"{scope}/{link}: unknown {noun} {reference}")


def _check_layouts(data: dict[str, Any], targets: list[dict[str, Any]]) -> None:
    for slide in data["slides"]:
        for variant in variants(data):
            layout = effective_style(data, slide, variant)["layout"]
            for target in targets:
                if not layout_allowed(layout, target):
                    raise ProjectError(
                        f"slides/{slide['id']}/variants/{variant['id']}: "
                        f"layout {layout} is incompatible with {target['id']}"
                    )


def project_assets(project: Project) -> set[Path]:
    """The resolved path of every image the project references, including its icon."""
    data = project.data
    values = [data["project"]["icon"]] if "icon" in data["project"] else []
    for slide in data["slides"]:
        for value in slide["assets"].values():
            values.extend(value.values() if isinstance(value, dict) else [value])
    return {resolve_asset(project, value) for value in values}


def _check_text_and_assets(project: Project) -> None:
    """Check that every slide has text for each locale and every referenced image resolves."""
    data = project.data
    project_assets(project)
    for slide in data["slides"]:
        for locale in data["locales"]:
            if locale not in slide["copy"]:
                raise ProjectError(f"slides/{slide['id']}/copy: missing {locale}")
