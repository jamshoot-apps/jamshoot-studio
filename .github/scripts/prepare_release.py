"""Validate a prepared release version and extract its Keep a Changelog notes."""

import argparse
import ast
import re
import sys
from datetime import date
from pathlib import Path


def prepare(root: Path, version: str) -> str:
    """The CHANGELOG notes for ``version``.

    Raises ValueError unless ``version`` is stable SemVer, equals ``__version__`` and has a
    dated entry with at least one change.
    """
    # Release metadata must be committed before dispatch
    if not re.fullmatch(r"(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)", version):
        raise ValueError("Version must be a stable SemVer such as 0.1.0 (without v).")
    tree = ast.parse((root / "src/jamshoot/__init__.py").read_text(encoding="utf-8"))
    package_version = next(
        ast.literal_eval(node.value)
        for node in tree.body
        if isinstance(node, ast.Assign)
        if any(
            isinstance(target, ast.Name) and target.id == "__version__" for target in node.targets
        )
    )
    if package_version != version:
        raise ValueError(f"Package version {package_version} does not match requested {version}.")
    changelog = (root / "CHANGELOG.md").read_text(encoding="utf-8")
    match = re.search(
        rf"^## \[{re.escape(version)}\] - (\d{{4}}-\d{{2}}-\d{{2}})\s*\n(.*?)(?=^## |\Z)",
        changelog,
        flags=re.MULTILINE | re.DOTALL,
    )
    if not match:
        raise ValueError(f"Missing dated CHANGELOG entry: ## [{version}] - YYYY-MM-DD")
    date.fromisoformat(match[1])
    notes = match[2].strip()
    if not notes or not re.search(r"^- \S", notes, flags=re.MULTILINE):
        raise ValueError("Release changelog must contain at least one change.")
    return notes + "\n"


def main() -> int:
    """Write the release notes to ``--output``; exit 1 on any failure."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--version", required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    try:
        notes = prepare(args.root, args.version)
        args.output.write_text(notes, encoding="utf-8")
    except (OSError, ValueError, SyntaxError, StopIteration) as error:
        print(f"Release preflight failed: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
