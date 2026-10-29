# Rendering

Studio's preview, Studio's export and the CLI use one Pillow renderer.
`auto` draws an app window for Mac and a device mockup for the other platforms.
`device-focus` (**Large device**) gives the screenshot more room. `raw` (**Image
only**) fills the size with a centered crop of the screenshot and draws no text or
background. Custom sizes show the screenshot with rounded corners, without a mockup.

## Images and text

- Screenshots: static PNG, JPEG or WebP, at most 24 million pixels. EXIF rotation
  is applied and transparency is flattened onto white. Use sRGB images: color
  profiles are not converted. Studio uploads are limited to 16 MiB and saved as PNG.
- `contain` (**Match screenshot**) keeps the whole screenshot; `cover` (**Crop to
  display**) crops its center to the mockup's screen. Screenshots are never rotated
  to match the output orientation, so check each size before exporting.
- Text wraps and shrinks to fit its box. Text that still does not fit fails with
  `Text overflow` instead of being clipped; spacing that leaves no room for the
  screenshot fails with `Layout overflow`.
- Right-to-left text and missing glyphs fail; complex-script shaping and emoji
  fallback are not supported.

## Fonts

No fonts are bundled or downloaded. Text without a named font uses an installed
sans-serif family: Helvetica Neue, Helvetica or Arial on macOS; Segoe UI or Arial
on Windows; DejaVu Sans, Noto Sans, Liberation Sans or Arial elsewhere. If none is
installed, install one (Linux: `fonts-dejavu-core`), choose a project font, or set
`JAMSHOOT_FONT` to a TTF, OTF or TTC file. `raw` needs no font.

`typography.<field>.font` names a family, looked up first in the project's
`assets/fonts`, then among installed fonts. Fonts uploaded in **Project →
Typography** travel with the project; installed fonts render only where installed.
`JAMSHOOT_FONT_DIRS` replaces the system font folders, separated like `PATH`.
Named families must resolve when planning.

The same project renders to the same pixels only with the same fonts, Pillow and
FreeType versions; `manifest.json` hashes are comparable only under those conditions.

## Export

Each output is an RGB PNG at the size's exact dimensions. `manifest.json` records
the renderer and catalog versions, the file count, and each PNG's size, path and
SHA-256. Paths follow the [output matrix](project-schema.md#output-matrix).

The CLI renders into a staging folder and publishes the batch when every file
succeeds; on a handled error it removes that run. A killed process can leave partial
output, so retry into a new folder. Studio creates missing parent folders and numbers
repeated exports. Both apply the [file limit](cli.md).

## Device mockups

Device mockups are drawn by code, as approximations rather than exact hardware or
Apple artwork; **Device frame** sets them to black, silver or none. Their geometry
is in [`render/devices.py`](https://github.com/jamshoot-apps/jamshoot-studio/blob/main/src/jamshoot/render/devices.py);
MacBook camera proportions are estimated from Apple's
[front view](https://support.apple.com/en-gb/126318).
