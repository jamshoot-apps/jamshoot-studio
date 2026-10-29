# CLI

Install as described in [Install](install.md). Every command has `--help`.

```sh
jamshoot init ./screenshots --json
# Replace screenshots/assets/screenshot.png with your app screenshot.
jamshoot validate ./screenshots/project.json --json
jamshoot plan ./screenshots/project.json --json
jamshoot render ./screenshots/project.json --out ./output --json
```

| Command | Behavior |
| --- | --- |
| `catalog` | Lists the built-in sizes: target IDs, platforms, dimensions and App Store display groups. It does not check that a submission is complete |
| `init DIR` | Creates the new folder `DIR` with `project.json`, a copy of the schema and a 1440×900 Mac placeholder screenshot |
| `validate FILE` | Checks structure, IDs, targets, text, referenced files and required screenshots. It does not decode images or lay out text |
| `plan FILE` | Lists every output file with its resolved settings, without rendering. Missing screenshots appear as `"source": null`; named fonts must resolve |
| `render FILE --out DIR` | Renders RGB PNGs and `manifest.json` into the new folder `DIR`, whose parent must exist. Needs every screenshot |
| `studio [FILE]` | Starts the browser editor; needs the `web` extra. See [Studio](studio.md) |

Text is laid out only when rendering: text that does not fit fails `render` (and
Studio's preview and export), not `validate` or `plan`. `render` reads
`project.json` from disk; Studio's **Export PNGs** renders the unsaved draft.

`plan`, `render` and `studio` refuse more than 1000 output files; raise the limit
with `--max-files N`. The count is slides × sizes × languages × variants; nothing
is skipped. Output paths are described in the [project format](project-schema.md#output-matrix).

## JSON output and exit codes

With `--json`, each command writes one JSON document to stdout. Exit code 0 means
success. A project or file error exits with 1 and prints
`{"error": {"code": "invalid_project", "message": "..."}}`; without `--json` the
message goes to stderr. Invalid arguments exit with 2 and argparse's message on
stderr. Option abbreviations are not accepted; `studio` has no `--json`.

`init` returns `{"project": "/abs/path/project.json"}`. `validate` returns
`{"valid": true, "project": "...", "version": 1}`. `catalog` returns the catalog
with `targets` and `displayGroups`. `plan` returns every output file:

```json
{
  "version": 1,
  "fileCount": 1,
  "files": [{
    "slide": "overview", "variant": "default", "locale": "en-US",
    "target": "appstore.mac.1280x800", "platform": "mac", "width": 1280, "height": 800,
    "output": "default/en-US/appstore.mac.1280x800/01-overview.png",
    "source": "/abs/path/assets/screenshot.png",
    "headline": "Your app at a glance",
    "layout": "window-top", "pattern": "dots", "seed": "launch",
    "deviceFrame": "black", "screenshotFit": "contain", "labelStyle": "text"
  }]
}
```

`render` returns the manifest it writes to `DIR/manifest.json`:

```json
{
  "version": 1,
  "rendererVersion": "1.0.0",
  "catalogVersion": 1,
  "fileCount": 1,
  "files": [{
    "slide": "overview", "variant": "default", "locale": "en-US",
    "target": "appstore.mac.1280x800", "width": 1280, "height": 800,
    "output": "default/en-US/appstore.mac.1280x800/01-overview.png",
    "sha256": "5bcc7978…"
  }]
}
```

## Studio options

```sh
jamshoot studio --open
jamshoot studio --home ./workspace --port 0 --open
jamshoot studio ./screenshots/project.json --out ./export-01 --open
```

| Option | Effect |
| --- | --- |
| `--open` | Opens the browser |
| `--port N` | Port on `127.0.0.1`; default 8765, `0` picks a free one |
| `--home DIR` | Uses `DIR/projects` and `DIR/trash` for this run |
| `--fallback-home DIR` | Studio folder when no `--home`, `JAMSHOOT_HOME` or saved setting chooses one |
| `FILE`, `--out DIR` | Also opens `FILE` in place; `--out` sets its export folder |
| `--max-files N` | Output file limit for preview and export |

## Environment variables

| Variable | Effect |
| --- | --- |
| `JAMSHOOT_HOME` | Studio folder |
| `JAMSHOOT_SETTINGS` | Location of Studio's settings file |
| `JAMSHOOT_FONT` | TTF, OTF or TTC file for text without a named font |
| `JAMSHOOT_FONT_DIRS` | Font folders to search instead of the system ones, separated like `PATH` |
