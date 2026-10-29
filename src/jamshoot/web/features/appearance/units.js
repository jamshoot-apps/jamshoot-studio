// Spacing and text sizes are stored as % of the canvas, so one value fits every size.
// Studio can show them as pixels of the previewed size instead, like a design tool; typed
// pixels are stored back as the matching %.

import { choices } from "../../shared/ui/choice-group/choice-group.js";
import { rangeControl } from "../../shared/ui/range-control/range-control.js";

const STORAGE_KEY = "jamshoot.units";
const UNITS = { percent: "%", px: "px" };
const listeners = new Set();

function stored() {
  try {
    return localStorage.getItem(STORAGE_KEY) === "px" ? "px" : "percent";
  } catch {
    return "percent";
  }
}

let unit = stored();

// One preference for every control; `onUnitChange` listeners redraw them.
function setUnit(next) {
  unit = next;
  try {
    localStorage.setItem(STORAGE_KEY, next);
  } catch {
    // Private windows keep the choice for this page only.
  }
  for (const listener of listeners) listener(next);
}

export function onUnitChange(listener) {
  listeners.add(listener);
}

// Widths run across the canvas; all other spacing runs down it.
export function spacingExtent(key, target) {
  const across = key.endsWith("_width");
  return across ? target.width : target.height;
}

// A "% | px" switch in `fieldset`; every switch shows the one preference.
export function unitSwitch(fieldset) {
  choices(fieldset, Object.keys(UNITS), unit, setUnit, (value) => UNITS[value]);
}

// Four decimals keep every typed pixel exact on canvases up to 8192 pixels.
const round4 = (value) => Math.round(value * 10000) / 10000;

function rangeBounds(caption, limits, pixels, factor) {
  return pixels
    ? {
        caption: `${caption} (px)`,
        minimum: Math.ceil(limits.minimum * factor),
        maximum: Math.floor(limits.maximum * factor),
        step: 1,
      }
    : { caption: `${caption} (%)`, minimum: limits.minimum, maximum: limits.maximum };
}

// A range control for a % of the canvas. `extent()` is how many pixels 100 % spans on the
// previewed size along this setting's axis.
export function measuredRange(container, id, caption, limits, onChange, session, extent) {
  let factor = 1;
  const control = rangeControl(
    container,
    id,
    `${caption} (%)`,
    limits,
    (value) => onChange(factor === 1 ? value : round4(value / factor)),
    session,
  );
  return {
    element: control.element,
    update(value) {
      const pixels = unit === "px" ? extent() : 0;
      factor = pixels ? pixels / 100 : 1;
      control.configure(rangeBounds(caption, limits, pixels, factor));
      control.update(pixels ? Math.round(value * factor) : value);
    },
  };
}
