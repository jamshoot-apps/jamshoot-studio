// The background row, color rows and pattern settings of one scope.

import { $ } from "../../shared/lib/dom.js";
import { paletteOf } from "../../shared/model/project.js";
import { gradientStops, hexToHSV, hsvToHex } from "../../shared/ui/color-picker/color.js";
import { colorControl } from "../../shared/ui/color-picker/color-row.js";
import { rangeControl, rangeSession } from "../../shared/ui/range-control/range-control.js";

// Rows below the background; the background row edits `top`, `bottom` and the gradient.
export const COLOR_LABELS = {
  accent: "Pattern",
  text: "Headline",
  muted: "Supporting text",
  frame: "Window frame",
};
const STROKE_PATTERNS = [
  "circles",
  "waves",
  "mesh",
  "diagonal",
  "grid",
  "arcs",
  "confetti",
  "crosshatch",
  "chevrons",
  "hexagons",
];

function patternTileURL(pattern, palette, seed) {
  const query = new URLSearchParams({
    top: palette.top.slice(1),
    bottom: palette.bottom.slice(1),
    accent: palette.accent.slice(1),
    seed: String(seed),
  });
  return `/pattern-preview/${pattern}?${query}`;
}

// The start color darkened, or lightened when it is already dark.
function gradientEnd(color) {
  const { h, s, v } = hexToHSV(color);
  return hsvToHex(h, s, v > 50 ? v - 30 : v + 30);
}

// The background as one color row: the swatch shows the fill and its picker edits the
// stops, the fill type and the gradient's shape. `write(key, value)` stores a color and
// `writeGradient(key, value)` a gradient setting.
export function backgroundControl(container, id, options) {
  const { schema, write, writeGradient, editSession = {}, onRevert, onReset } = options;
  let colors = {},
    gradient = {};
  const source = {
    limits: schema.$defs.gradient.properties,
    read: () => ({ colors, gradient }),
    // Leaving solid with one color everywhere gives the gradient a visible second color.
    set(key, value) {
      const stops = gradientStops(colors, gradient);
      if (key === "kind" && value !== "solid" && stops.every((stop) => stop.color === colors.top))
        source.setStops([stops[0], { ...stops.at(-1), color: gradientEnd(colors.top) }]);
      writeGradient(key, value);
    },
    // Stops in position order; the start and end colors follow the outer stops, so palettes
    // and pattern previews keep showing the fill's ends.
    setStops(stops) {
      writeGradient("stops", stops);
      write("top", stops[0].color);
      write("bottom", stops.at(-1).color);
    },
  };
  const row = colorControl(container, id, "Background", (hex) => write("top", hex), {
    onStart: () => editSession.onStart?.("Edit background"),
    onEnd: () => editSession.onEnd?.(),
    onRevert,
    onReset,
    gradient: source,
  });
  return {
    element: row.element,
    // `nextGradient` is complete (defaults applied).
    update(nextColors, nextGradient) {
      colors = nextColors;
      gradient = nextGradient;
      row.showFill(colors, gradient);
    },
    setOverridden: (overridden) => row.setOverridden(overridden),
  };
}

const RANGE_CAPTIONS = {
  density: "Density (%)",
  opacity: "Opacity (%)",
  scale: "Scale (%)",
  rotation: "Rotation (°)",
  strokeWidth: "Stroke width",
  amplitude: "Wave amplitude (%)",
};

function rangeApplies(key, pattern) {
  if (key === "amplitude") return pattern === "waves" || pattern === "mesh";
  if (key === "strokeWidth") return STROKE_PATTERNS.includes(pattern);
  return true;
}

function tileImage(span) {
  const existing = span.querySelector("img");
  if (existing) return existing;
  const image = document.createElement("img");
  image.alt = "";
  image.width = 160;
  image.height = 96;
  image.decoding = "async";
  span.prepend(image);
  return image;
}

function paintTile(span, url) {
  const image = tileImage(span);
  if (image.getAttribute("src") !== url) image.src = url;
}

// Prefix "" is the slide, "default-" the project.
class AppearanceControls {
  overrides = {};
  ranges = {};
  tileTimer = 0;

  constructor(prefix, { schema, appearance, change, reset, editSession = {} }) {
    Object.assign(this, { prefix, appearance, change, reset, editSession });
    const list = $(`${prefix}colors`);
    let original;
    this.background = backgroundControl(list, `${prefix}background`, {
      schema,
      write: (key, value) => change("colors", key, value),
      writeGradient: (key, value) => change("gradient", key, value),
      editSession: {
        onStart: (label) => {
          original = this.#ownBackground();
          editSession.onStart?.(label);
        },
        onEnd: editSession.onEnd,
      },
      onRevert: () => this.#revertBackground(original),
      onReset: () => reset("background"),
    });
    this.colors = {};
    for (const key of Object.keys(COLOR_LABELS)) this.colors[key] = this.#colorRow(key, list);
    for (const [key, limits] of Object.entries(schema.$defs.patternSettings.properties)) {
      const id = `${prefix}pattern-${key}`;
      const onChange = (value) => change("patternSettings", key, value);
      this.ranges[key] = rangeControl(
        $(`${prefix}pattern-settings`),
        id,
        RANGE_CAPTIONS[key],
        limits,
        onChange,
        rangeSession(editSession, "Adjust pattern"),
      );
    }
    $(`${prefix}reset-colors`).addEventListener("click", () => reset("palette"));
    $(`${prefix}reset-pattern-settings`).addEventListener("click", () => reset("patternSettings"));
  }

  #colorRow(key, container, onChange = (value) => this.change("colors", key, value)) {
    let original;
    return colorControl(container, `${this.prefix}color-${key}`, COLOR_LABELS[key], onChange, {
      onEnd: this.editSession.onEnd,
      onStart: () => {
        original = this.overrides[key];
        this.editSession.onStart?.();
      },
      onRevert: () => this.#revert(key, original),
      onReset: () => this.reset("colors", key),
    });
  }

  // The scope's own start, end and gradient values.
  #ownBackground() {
    const { top, bottom } = this.own.colors;
    const colors = Object.fromEntries(
      Object.entries({ top, bottom }).filter(([, value]) => value !== undefined),
    );
    return { colors, gradient: { ...this.own.gradient } };
  }

  // Back to the background from before the picker opened, inheritance included.
  #revertBackground(original) {
    this.reset("background", null, { restoreInheritance: false });
    for (const [key, value] of Object.entries(original.colors)) this.change("colors", key, value);
    for (const [key, value] of Object.entries(original.gradient))
      this.change("gradient", key, value);
  }

  // Back to the color from before the picker opened; an inherited one drops the override.
  #revert(key, original) {
    if (original === undefined) this.reset("colors", key, { restoreInheritance: false });
    else this.change("colors", key, original);
  }

  // `style` is resolved; `ownStyle` holds only the scope's own values.
  update(style, ownStyle = {}, disabled = false, { showWindowFrame = true } = {}) {
    const { prefix, appearance } = this;
    const own = { colors: {}, gradient: {}, patternSettings: {}, ...ownStyle };
    const palette = paletteOf(appearance, style);
    this.own = own;
    this.overrides = { ...own.colors };
    this.#updateColors(palette, own, style);
    this.colors.frame.element.hidden = !showWindowFrame;
    const noPattern = this.#updateRanges(style);
    $(`${prefix}pattern-settings-empty`).hidden = !noPattern;
    $(`${prefix}colors`).disabled = disabled;
    $(`${prefix}pattern-settings`).disabled = disabled || noPattern;
    const changed = Object.keys({ ...own.colors, ...own.gradient }).length > 0;
    $(`${prefix}reset-colors`).hidden = !changed;
    $(`${prefix}reset-colors`).disabled = disabled;
    $(`${prefix}reset-pattern-settings`).disabled =
      disabled || noPattern || !Object.keys(own.patternSettings).length;
    this.#scheduleTiles(palette, style.seed);
  }

  #updateColors(palette, own, style) {
    for (const [key, control] of Object.entries(this.colors)) {
      control.update(palette[key]);
      control.setOverridden(Object.hasOwn(own.colors, key));
    }
    this.background.update(palette, { ...this.appearance.gradientDefaults, ...style.gradient });
    this.background.setOverridden(
      ["top", "bottom"].some((key) => Object.hasOwn(own.colors, key)) ||
        Object.keys(own.gradient).length > 0,
    );
  }

  // Hides settings the pattern does not use; returns whether there is no pattern.
  #updateRanges(style) {
    const settings = { ...this.appearance.patternDefaults, ...style.patternSettings };
    const noPattern = style.pattern === "none";
    for (const [key, control] of Object.entries(this.ranges)) {
      control.update(settings[key]);
      control.element.hidden = noPattern || !rangeApplies(key, style.pattern);
    }
    return noPattern;
  }

  // Debounced so dragging a color does not request every pattern tile per frame.
  #scheduleTiles(palette, seed) {
    clearTimeout(this.tileTimer);
    const spans = [...$(`${this.prefix}pattern`).querySelectorAll(".choice > span")];
    const first = spans.some((span) => !span.querySelector("img"));
    const paint = () => {
      for (const span of spans)
        paintTile(span, patternTileURL(span.previousElementSibling.value, palette, seed));
    };
    this.tileTimer = setTimeout(paint, first ? 0 : 300);
  }
}

export function appearanceControls(prefix, options) {
  return new AppearanceControls(prefix, options);
}
