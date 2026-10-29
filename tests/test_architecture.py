"""Package import boundaries and the lint suppression policy."""

import ast
import json
import re
import tomllib
import unittest
from importlib.resources import files
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Comments that switch a linter or type checker off for a line or a file.
SUPPRESSION = re.compile(r"#\s*(pylint:\s*disable|type:\s*ignore|pyright:\s*ignore|noqa)")
# The same for Studio's browser code: Biome, Fallow and the usual JavaScript tools.
WEB_SUPPRESSION = re.compile(
    r"(biome|fallow|eslint|stylelint)-(ignore|disable)|@ts-(ignore|nocheck|expect-error)"
)
WEB_SOURCES = {".js", ".mjs", ".css", ".html"}


class ArchitectureTests(unittest.TestCase):
    """Import boundaries of ``core`` and ``render``, and the lint configuration."""

    def test_core_and_renderer_do_not_import_the_server_or_browser_tools(self):
        """``core`` and ``render`` import no server or browser code, and ``core`` no renderer."""
        package = files("jamshoot")
        for module in ("core", "render"):
            for source in package.joinpath(module).iterdir():
                if not source.name.endswith(".py"):
                    continue
                tree = ast.parse(source.read_text("utf-8"))
                imports: list[str] = []
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        imports.extend(alias.name for alias in node.names)
                    elif isinstance(node, ast.ImportFrom):
                        imports.append(node.module or "")
                forbidden = ("bottle", "jamshoot.server", "playwright", "selenium")
                self.assertFalse(any(name.startswith(forbidden) for name in imports), source.name)
                if module == "core":
                    self.assertFalse(any(name.startswith("jamshoot.render") for name in imports))

    def test_sources_fix_lint_findings_instead_of_silencing_them(self):
        """Python sources have no suppression comments, and pylint keeps its default checks."""
        for folder in ("src", "tests", "typings"):
            for path in (ROOT / folder).rglob("*.py*"):
                if path.suffix not in {".py", ".pyi"}:
                    continue
                for number, line in enumerate(path.read_text("utf-8").splitlines(), 1):
                    with self.subTest(path=path.relative_to(ROOT), line=number):
                        self.assertIsNone(SUPPRESSION.search(line), line)
        pylint = tomllib.loads((ROOT / "pyproject.toml").read_text("utf-8"))["tool"]["pylint"]
        # Disabled messages, raised design limits or a looser duplicate check would hide findings.
        for section in ("messages control", "design", "similarities"):
            self.assertNotIn(section, pylint)

    def test_studio_code_fixes_findings_instead_of_silencing_them(self):
        """Web sources have no suppression comments; Biome and Fallow keep their default rules."""
        vendor = ROOT / "src/jamshoot/web/vendor"
        sources = [*(ROOT / "src/jamshoot/web").rglob("*"), *(ROOT / "tests").rglob("*")]
        for path in sources:
            if path.suffix not in WEB_SOURCES or path.is_relative_to(vendor):
                continue
            for number, line in enumerate(path.read_text("utf-8").splitlines(), 1):
                with self.subTest(path=path.relative_to(ROOT), line=number):
                    self.assertIsNone(WEB_SUPPRESSION.search(line), line)
        biome = json.loads((ROOT / "biome.json").read_text("utf-8"))
        self.assertNotIn("rules", biome.get("linter", {}))
        self.assertNotIn("overrides", biome)
        fallow = json.loads((ROOT / ".fallowrc.json").read_text("utf-8"))
        # Only entry points, vendored code and Node unit coverage are configured.
        self.assertEqual(set(fallow), {"$schema", "entry", "ignorePatterns", "health"})
        self.assertEqual(fallow["health"], {"coverage": "coverage/node"})
        self.assertEqual(set(fallow["ignorePatterns"]), {"src/jamshoot/web/vendor/**"})
