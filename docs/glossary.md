# Glossary

Studio, the CLI and `project.json` use one set of terms. Where the editor label
differs from the JSON key, both are listed. JSON keys are camelCase.

| Term | Editor label | JSON / CLI | Meaning |
| --- | --- | --- | --- |
| Studio | — | `./studio`, `jamshoot studio` | The local browser editor, started by the launcher script or the CLI command |
| Project | Project | `project.json` | A folder with `project.json`, its `assets/` and fonts; portable as a ZIP |
| Studio folder | Settings → Studio folder | `--home`, `JAMSHOOT_HOME` | Where Studio keeps `projects/` and `trash/` |
| Trash | Remove | `trash/` | Where removed projects go; move a folder back to restore it |
| Draft | Unsaved changes | — | Edits in the browser that **Save** has not written to `project.json` yet |
| Slide | Slides | `slides[]` | One screenshot design with its text, screenshots and optional `style`; 1–10 per project |
| Language | Language, Languages | `locales[]` | A locale code such as `en-US`, also used as a folder name; every slide needs a headline in each |
| Variant | Variant, Variants | `variants[]` | An alternative of the whole set, such as light and dark, with its own appearance overrides; without `variants` there is one, `default` |
| Platform | Platforms and sizes | `assets` keys | `iphone`, `iphone-duo`, `ipad`, `mac` or `custom`; all sizes of a platform share one screenshot |
| Size | Size, Platforms and sizes | `targets[]`, `jamshoot catalog` | One output size: a catalog ID such as `appstore.iphone.1320x2868`, or `custom.<width>x<height>` |
| iPhone Duo | Duo | `iphone-duo` | Sizes for the iPhone Duo's outer and inner displays, with their own screenshot |
| Screenshot | Screenshot | `assets` | Your app screenshot for a platform, optionally one per language; PNG, JPEG or WebP inside the project |
| Text | Headline, Supporting text, Feature label | `copy[locale]` | `headline` (required), `subtitle` and `featureLabel` |
| Feature label | Feature label, Eyebrow | `featureLabel`, `labelStyle` | Short text above the headline, drawn as plain `text` or a `badge` |
| Appearance | Appearance | `defaults`, variant fields, slide `style` | Visual settings, resolved as built-in values → project defaults → variant → slide |
| Override | Customize on this slide, Reset | slide `style` | A value set on a slide instead of inherited; **Reset** removes it |
| Layout | Layout | `layout` | Composition: Automatic (`auto`), App window (`window-top`), Device (`device-top`), Large device (`device-focus`), Image only (`raw`) |
| Device mockup | Device, Large device | `device-top`, `device-focus` | The drawn hardware around the screenshot; "device" in Studio always means this |
| Device frame | Device frame | `deviceFrame` | Mockup finish: `black`, `silver` or `none` |
| Screenshot fit | Screen | `screenshotFit` | Match screenshot (`contain`) or Crop to display (`cover`) |
| Spacing | Spacing | `layoutSettings` | Margins, gaps, text and screenshot widths, screenshot top |
| Layout template | Layout templates | `layoutStyles[]`, `layoutStyle` | A named, reusable set of spacing values, linked by id |
| Colors | Colors | `colors` | Six roles: `top`, `bottom`, `accent`, `text`, `muted`, `frame` |
| Palette | Palettes | `colorStyles[]`, `colorStyle` | A named, reusable set of colors and an optional gradient, linked by id |
| Starter palette | Starter palettes | — | A built-in palette (Ocean, Graphite, Mint, Sunset, Lavender, Sand, Rose, Midnight) that Studio copies into the project's palettes when chosen; without a palette, Ocean's colors apply |
| Gradient | Background → Fill | `gradient` | Linear, radial or solid background fill, optionally through color stops |
| Pattern | Background pattern | `pattern`, `patternSettings` | Decoration drawn over the background |
| Seed | Arrangement seed | `seed` | Any text; the same seed repeats the same pattern arrangement |
| Glow | — (Project JSON) | `glows[]` | Soft light painted over the fill and under the pattern |
| Typography | Typography | `typography` | Per text field: font, size, weight, line height, letter spacing, case |
| Plan | — | `jamshoot plan` | Every output file with its resolved settings, listed without rendering; `"source": null` marks a missing screenshot |
| Export | Export PNGs | `jamshoot render` | Renders every variant × language × size × slide into PNGs and `manifest.json` |
| Manifest | — | `manifest.json` | Export record: versions, `fileCount`, sizes, paths and SHA-256 of each PNG |
