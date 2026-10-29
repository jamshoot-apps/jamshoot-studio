# Troubleshooting

| Symptom | Fix |
| --- | --- |
| `python3: command not found` or a version below 3.11 | Install Python 3.11 or newer, then run `./studio` or the [install](install.md) steps again |
| Studio does not start: address already in use | Start it on a free port: `./studio --port 0` or `jamshoot studio --port 0 --open` |
| The page refuses to load on `localhost` | Open the exact `http://127.0.0.1:PORT` address Studio prints |
| `Studio requires the optional web extra` | Install the editor: `python -m pip install -e '.[web]'` |
| `Font unavailable` | Install a sans-serif font (Linux: `fonts-dejavu-core`), upload one in **Project → Typography**, or set `JAMSHOOT_FONT`. See [Rendering](rendering.md#fonts) |
| `Text overflow` | Shorten the text, or lower its size or spacing in typography |
| `Layout overflow` | Reduce margins and gaps, or the text, so the screenshot has room |
| RTL text or missing glyphs fail | Use a font with those glyphs; right-to-left and complex scripts are not supported. See [Rendering](rendering.md#images-and-text) |
| Missing screenshots | Add a screenshot for every slide and exported platform; **Project → General** lists the slides that lack one |
| Plan exceeds the file limit | Remove sizes, languages or variants, or raise `--max-files` |
| `render` refuses the output folder | Use a new folder whose parent exists |
| Save reports a change on disk | Copy your draft's JSON, compare it with the file, then reload |
| Output differs between machines | Use the same fonts and Pillow version; see [Rendering](rendering.md#fonts) |
