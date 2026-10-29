# Project format v1

The [bundled JSON Schema](https://github.com/jamshoot-apps/jamshoot-studio/blob/main/src/jamshoot/data/project.schema.json) defines all fields
and numeric limits. `jamshoot init` copies it beside `project.json` for offline
editor completion; runtime validation always uses the bundled version.

## Minimal project

Create `assets/screenshot.png` inside the project folder before using this example:

```json
{
  "$schema": "./project.schema.json",
  "version": 1,
  "project": {"name": "Example App"},
  "targets": ["appstore.mac.1280x800"],
  "locales": ["en-US"],
  "defaults": {"layout": "auto", "pattern": "dots", "seed": "launch"},
  "slides": [{
    "id": "overview",
    "copy": {"en-US": {"headline": "Your app at a glance"}},
    "assets": {"mac": "assets/screenshot.png"}
  }]
}
```

| Field | Meaning |
| --- | --- |
| `version` | Integer `1` |
| `project` | Required nonblank `name`; optional local `icon` |
| `targets` | Unique IDs from `jamshoot catalog`, or `custom.<width>x<height>` (64–8192 px per side, at most 24 million pixels) |
| `locales` | Unique languages, preferably locale codes such as `en-US`; each is also an output folder name, so `/`, `:` and similar characters are rejected, as are case-insensitive duplicates |
| `defaults` | Required `layout`, `pattern`, `seed`, plus optional appearance settings |
| `slides` | 1–10 slides, each with a unique `id`, localized `copy`, `assets`, optional display `name` and appearance `style` |
| `variants` | Optional nonempty list of `{id, ...appearance overrides}`; omission means one variant named `default` |
| `colorStyles`, `layoutStyles` | Optional libraries of named project palettes and layout templates |

Keys are camelCase. IDs start with a lowercase letter, contain lowercase letters,
digits or hyphens, and have at most 64 characters. Windows reserved names are rejected.
Unknown configuration properties, duplicate JSON keys, NaN and Infinity are errors.

## Languages and screenshots

Every slide needs a nonblank `copy[locale].headline` for each project language.
`subtitle` and `featureLabel` (eyebrow) are optional. Text is never translated or
borrowed from another language.

Assets map a platform (`mac`, `iphone`, `iphone-duo`, `ipad`, `custom`) to a path
shared by all languages, or a locale/path map:

```json
{"iphone": {"en-US": "assets/en.png", "ru": "assets/ru.png"}}
```

All sizes of a platform share its screenshot. Duo uses `iphone-duo`, and all custom
sizes use `custom`. Paths must be relative, use `/`, and refer to existing
PNG/JPEG/WebP files inside the project. URLs, absolute paths, `..` and symlinks
escaping the project are rejected.

A draft may have `assets: {}` or an incomplete locale map. Studio can save and
preview it; `plan` returns `"source": null` for missing screenshots. `validate`,
`render` and Studio export require every selected platform/language screenshot.

## Appearance

Effective style = built-in values → project defaults → variant → slide `style`.
Slide appearance applies across languages, targets and variants. Remove an
override to inherit again. Colors, gradient, pattern settings and layout settings
merge per field; typography merges per text field and setting. Arrays such as
gradient stops and glows replace the inherited array.

| Field | Use |
| --- | --- |
| `layout` | `auto` chooses `window-top` for Mac and `device-top` otherwise; `window-top` requires Mac; `device-top` and `device-focus` draw a device mockup; `raw` fills the output with a centered crop and draws no text or background |
| `colors` | Partial `#RRGGBB` values: `top`, `bottom`, `accent`, `text`, `muted`, `frame` |
| `gradient` | `kind`: `linear`, `radial`, `solid`; `angle`, or radial `centerX`, `centerY`, `radius`; `midpoint`; optional 2–8 `{color, position}` stops |
| `pattern`, `seed` | `none`, `dots`, `circles`, `waves`, `diagonal`, `grid`, `confetti`, `arcs`, `mesh`, `crosshatch`, `chevrons`, `hexagons`, `stars` or `checkerboard`; any `seed` text repeats one arrangement |
| `patternSettings` | `density`, `opacity`, `scale`, `rotation`, `strokeWidth` and wave `amplitude` |
| `deviceFrame`, `screenshotFit` | `black`, `silver`, `none`; `contain` keeps the screenshot, `cover` crops its center |
| `layoutSettings` | `topMargin`, `labelGap`, `subtitleGap`, `screenshotGap`, `screenshotTop`, `bottomMargin` (% of canvas height); `textWidth`, `screenshotWidth` (% of canvas width) |
| `typography` | Per `featureLabel`, `headline`, `subtitle`: `font` family, `size` (% of canvas height), `weight`, `lineHeight` (% of size), `letterSpacing` (% of size), `uppercase`; unset values use the layout's built-in text |
| `labelStyle` | `text` or `badge` eyebrow |
| `glows` | Up to eight `{x, y, radius, color, opacity, blur}` lights; edit in JSON; `[]` disables inherited glows |

For example, a slide can override only its headline size and pattern:

```json
"style": {"typography": {"headline": {"size": 5}}, "pattern": "waves"}
```

Palettes contain `id`, `name`, all six `colors`, and optional `gradient`.
Layout templates contain `id`, `name`, `layoutSettings`. Reference them with
`colorStyle` or `layoutStyle` in defaults, variants or slide style. A reference
restarts its value groups from that saved definition, then applies explicit
overrides. Omit the reference to inherit; `null` resets the group to built-in
values before local overrides. Studio preserves linked values when deleting a
definition. Without a palette or `colors`, the built-in Ocean colors apply. Studio's
starter palettes are copied into `colorStyles` when chosen, so a project never
depends on them.

## Output matrix

Files expand in configuration order: variant → locale → target → slide.
Each combination produces one PNG, with its slide's 1-based position in the name:

```text
{variant}/{locale}/{target}/{position}-{slide-id}.png
default/en-US/appstore.mac.1280x800/01-overview.png
```

Use `jamshoot plan project.json --json` to inspect the resolved settings, sources
and paths before rendering. See [CLI](cli.md) for batch limits,
[Rendering](rendering.md) for image/font requirements and the
[glossary](glossary.md) for how editor labels map to these keys.
