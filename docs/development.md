# Development

## Setup and checks

Clone the repository and create `.venv` as in [Install](install.md), then:

```sh
python -m pip install -e '.[dev,web]'
npm ci
```

Node.js 22+ is used only for checks of the browser code. Tests use `unittest`; the
`web` extra enables the HTTP tests, and rendering tests need an installed
sans-serif font or `JAMSHOOT_FONT`.

Every pull request must pass:

```sh
python -m unittest discover -s tests -v
python -m ruff check .
python -m ruff format --check .
python -m black --check .
python -m mypy
python -m pyright
python -m pylint src tests
npm run check
```

Ruff and Black share one style; both run so either formatter keeps it.
`npm run check` runs Biome (lint and format), the Node unit tests and Fallow (dead
code and complexity); `npm run format` applies safe fixes. The Node tests cover
editor state, history, shortcuts, color math and the API client without a browser.

Packaging changes also need:

```sh
python -m build --outdir ./dist-check
python tests/check_distribution.py ./dist-check
```

Use an empty `dist-check`: the check expects one wheel and one sdist. CI installs
the built wheel and runs the tests on macOS, Linux and Windows with Python 3.11
and 3.14. Before a release, check create, edit, save, export, ZIP transfer,
Undo/Redo and error recovery by hand at desktop and mobile widths, in the light and
dark themes.

## Code organization

```text
src/jamshoot/
  core/       project rules: schema, styles, planning, starter projects
  render/     Pillow renderer: background, text, device mockups, export
  server/     Studio's local HTTP server
  web/        Studio's browser code: pages/, features/, shared/
  data/       schema, catalog and settings shipped with the package
  cli.py      the jamshoot command
  *.py        catalog, project library, settings and font lookup
tests/        Python and Node tests
docs/         this documentation (MkDocs)
studio        the ./studio launcher
```

The CLI and the server share project rules and the renderer; `core` and `render`
never import the server or browser code. Runtime files load through
`importlib.resources`, so an installed wheel behaves like the checkout.

Browser code is native ES modules without a build step. Each page keeps its HTML,
JavaScript and CSS together; features are grouped by what they do; each reusable UI
component has its own folder. Pages use features, features use shared code, and
shared code depends on neither. Import from the owning module, load component
styles before feature and page overrides, and keep CSS layers. HTML is served
through page routes and other files through an allowlist.

Tests must run against an installed wheel. Architecture and design tests check
module boundaries, CSS tokens, contrast and lint suppressions.

## Documentation

`docs/` is rendered by MkDocs with `mkdocs.yml`. Preview with live reload at
http://127.0.0.1:8000:

```sh
python -m mkdocs serve
```

The **Publish documentation** workflow runs `python -m mkdocs build --strict`,
which fails on broken links, and deploys `site/` to GitHub Pages (Pages source:
**GitHub Actions**).

## Releases

The version is in `src/jamshoot/__init__.py`; archive contents are listed in
`pyproject.toml`. Record user-facing changes in
[CHANGELOG.md](https://github.com/jamshoot-apps/jamshoot-studio/blob/main/CHANGELOG.md)
under `Unreleased` and move them under `## [VERSION] - YYYY-MM-DD` for a release.

GitHub workflows run only when started by hand: **CI**, **Publish documentation**
and **Create tag and release**. The release workflow checks that the version and
dated changelog entry match, runs every check, then creates the `vVERSION` tag and
a GitHub Release with the wheel and sdist. It refuses an existing tag and does not
publish to PyPI. If the release fails after the tag was pushed, delete the tag with
`git push origin :refs/tags/vVERSION` before retrying.
