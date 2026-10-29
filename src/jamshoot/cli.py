"""The ``jamshoot`` command: the catalog listing, the project commands and Studio."""

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from jamshoot import __version__
from jamshoot.catalog import load_catalog
from jamshoot.core.planning import plan_project
from jamshoot.core.project import ProjectError, load_project, require_screenshots
from jamshoot.core.starter import init_project
from jamshoot.library import InPlace
from jamshoot.render.export import render_project
from jamshoot.settings import Homes

# Bottle is only needed for Studio.
STUDIO: Callable[..., None] | None
try:
    from jamshoot.server import serve
except ModuleNotFoundError as error:
    if error.name != "bottle":
        raise
    STUDIO = None
else:
    STUDIO = serve

PROJECT_COMMANDS = {
    "init": "Create a valid starter project in a new directory",
    "validate": "Validate a project and its local image references",
    "plan": "List planned PNG files without rendering",
    "render": "Render RGB PNGs and a manifest into a new directory",
}


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="jamshoot",
        description="JamShoot Studio: compose portable App Store screenshots locally.",
        allow_abbrev=False,
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    catalog = commands.add_parser(
        "catalog", help="List App Store output sizes for Mac, iPhone and iPad", allow_abbrev=False
    )
    catalog.add_argument("--json", action="store_true", help="Write a JSON catalog to stdout")
    for name, help_text in PROJECT_COMMANDS.items():
        command = commands.add_parser(name, help=help_text, allow_abbrev=False)
        command.add_argument("path", type=Path)
        command.add_argument("--json", action="store_true", help="Write a JSON result to stdout")
        if name in {"plan", "render"}:
            _max_files(command)
        if name == "render":
            command.add_argument("--out", type=Path, required=True, help="New export directory")
    studio = commands.add_parser(
        "studio", help="Start the optional local browser editor", allow_abbrev=False
    )
    studio.add_argument(
        "path", type=Path, nargs="?", help="Also open this project.json in place for this run"
    )
    _max_files(studio)
    studio.add_argument("--out", type=Path, help="Export directory for the opened project")
    studio.add_argument(
        "--home",
        type=Path,
        help="Folder holding projects/ and trash/ for this run (default: $JAMSHOOT_HOME, "
        "else the folder saved in Studio's settings)",
    )
    studio.add_argument(
        "--fallback-home",
        type=Path,
        help="Folder used when neither --home, $JAMSHOOT_HOME nor a saved setting chooses one",
    )
    studio.add_argument("--port", type=int, default=8765, help="Loopback port (default: 8765)")
    studio.add_argument("--open", action="store_true", help="Open Studio in the default browser")
    return parser


def _max_files(command: argparse.ArgumentParser) -> None:
    command.add_argument(
        "--max-files", type=int, default=1000, help="Maximum files in a plan (default: 1000)"
    )


def _run(args: argparse.Namespace) -> dict[str, Any]:
    """Run one project command and return its JSON-serializable result."""
    if args.command == "init":
        return {"project": str(init_project(args.path))}
    project = load_project(args.path)
    if args.command == "plan":
        return plan_project(project, max_files=args.max_files)
    if args.command == "render":
        return render_project(project, args.out, max_files=args.max_files)
    require_screenshots(project)
    return {"valid": True, "project": str(project.path), "version": 1}


def _print_result(args: argparse.Namespace, result: dict[str, Any]) -> None:
    if args.json:
        print(json.dumps(result, ensure_ascii=True, indent=2))
    elif args.command in {"plan", "render"}:
        print(f"{result['fileCount']} files")
        for item in result["files"]:
            print(item["output"])
    else:
        print(result["project"])


def _studio(args: argparse.Namespace) -> None:
    if STUDIO is None:
        raise ProjectError("Studio requires the optional web extra: install 'jamshoot-studio[web]'")
    if args.out and not args.path:
        raise ProjectError("--out requires a project path")
    STUDIO(
        InPlace(args.path, args.out) if args.path else None,
        homes=Homes(args.home, args.fallback_home),
        port=args.port,
        max_files=args.max_files,
        open_browser=args.open,
    )


def _print_catalog(as_json: bool) -> None:
    catalog = load_catalog()
    if as_json:
        print(json.dumps(catalog, ensure_ascii=True, indent=2))
        return
    print("TARGET  SIZE (px)")
    for target in catalog["targets"]:
        print(f"{target['id']}  {target['width']}x{target['height']}")


def main(argv: list[str] | None = None) -> int:
    """Run the CLI and return its exit code."""
    args = _parser().parse_args(argv)
    if args.command == "catalog":
        _print_catalog(args.json)
        return 0
    try:
        if args.command == "studio":
            _studio(args)
            return 0
        result = _run(args)
    except ProjectError as error:
        if getattr(args, "json", False):
            print(json.dumps({"error": {"code": "invalid_project", "message": str(error)}}))
        else:
            print(str(error), file=sys.stderr)
        return 1
    _print_result(args, result)
    return 0
