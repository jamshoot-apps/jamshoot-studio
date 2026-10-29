"""GitHub Actions policy: manual-only, pinned, and never publishing to PyPI."""

import re
import unittest
from pathlib import Path

import yaml


class WorkflowTests(unittest.TestCase):
    """Workflow triggers, pinned actions, and the Pages and release jobs."""

    def workflows(self):
        """Each workflow file by name, with YAML scalars left as strings."""
        root = Path(__file__).resolve().parents[1] / ".github/workflows"
        return {
            p.name: yaml.load(p.read_text(), Loader=yaml.BaseLoader)
            for p in root.iterdir()
            if p.suffix in {".yml", ".yaml"}
        }

    def test_all_workflows_are_manual_only(self):
        """Every workflow's only trigger is ``workflow_dispatch``."""
        workflows = self.workflows()
        self.assertTrue(workflows)
        for name, workflow in workflows.items():
            with self.subTest(name=name):
                self.assertEqual(set(workflow["on"]), {"workflow_dispatch"})

    def test_actions_are_pinned_to_commit_shas(self):
        """Every action is pinned to a full commit SHA with its release tag as a comment."""
        pinned = re.compile(r"uses: [\w.-]+/[\w./-]+@[0-9a-f]{40} # v\d+\.\d+\.\d+$")
        root = Path(__file__).resolve().parents[1] / ".github/workflows"
        uses_lines = [
            line.strip()
            for path in sorted(root.iterdir())
            if path.suffix in {".yml", ".yaml"}
            for line in path.read_text().splitlines()
            if "uses:" in line
        ]
        self.assertTrue(uses_lines)
        for line in uses_lines:
            with self.subTest(line=line):
                self.assertRegex(line, pinned)

    def test_pages_builds_docs_with_mkdocs_and_deploys_a_static_artifact(self):
        """Pages runs the strict MkDocs build; a separate job with ``pages: write`` deploys it."""
        workflow = self.workflows()["pages.yml"]
        build = workflow["jobs"]["build"]
        commands = [step.get("run") for step in build["steps"]]
        self.assertIn("python -m mkdocs build --strict", commands)
        upload = next(s for s in build["steps"] if "upload-pages-artifact" in s.get("uses", ""))
        self.assertEqual(upload["with"]["path"], "./site")
        self.assertEqual(workflow["jobs"]["deploy"]["needs"], "build")
        self.assertEqual(workflow["jobs"]["deploy"]["permissions"]["pages"], "write")

    def test_release_has_explicit_version_and_no_pypi_publish(self):
        """Releases need an explicit version, verify the tag and skip PyPI."""
        workflow = self.workflows()["release.yml"]
        self.assertEqual(
            workflow["on"]["workflow_dispatch"]["inputs"]["version"]["required"], "true"
        )
        self.assertEqual(workflow["jobs"]["release"]["permissions"]["contents"], "write")
        text = str(workflow)
        self.assertIn("prepare_release.py", text)
        self.assertIn("--verify-tag", text)
        self.assertNotIn("pypa/gh-action-pypi-publish", text)

    def test_ci_and_release_gate_studio_static_checks(self):
        """CI and release jobs run ``npm ci`` and ``npm run check``."""
        workflows = self.workflows()
        steps = {
            "ci.yml": workflows["ci.yml"]["jobs"]["web"]["steps"],
            "release.yml": workflows["release.yml"]["jobs"]["release"]["steps"],
        }
        for name, job_steps in steps.items():
            with self.subTest(name=name):
                commands = [step.get("run") for step in job_steps]
                self.assertIn("npm ci", commands)
                self.assertIn("npm run check", commands)
