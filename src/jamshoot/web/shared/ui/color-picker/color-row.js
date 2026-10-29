// A compact color row: label, swatch and HEX value; it opens the shared picker. A background
// row shows its whole fill and its picker also edits the gradient.
import { cssGradient } from "./color.js";
import { openPicker, syncPicker } from "./color-picker.js";

const FILL_NAMES = { linear: "Linear", radial: "Radial" };

function colorRowMarkup(id) {
  const row = document.createElement("div"),
    label = document.createElement("label"),
    button = document.createElement("button");
  const swatch = document.createElement("span"),
    code = document.createElement("span");
  row.className = "color-row";
  label.htmlFor = id;
  button.type = "button";
  button.id = id;
  button.className = "color-row-trigger";
  button.setAttribute("aria-haspopup", "dialog");
  swatch.className = "color-row-swatch";
  swatch.setAttribute("aria-hidden", "true");
  code.className = "color-row-code";
  code.id = `${id}-value`;
  button.setAttribute("aria-describedby", code.id);
  button.append(swatch, code);
  row.append(label, button);
  return { row, label, button, swatch, code };
}

function resetButton(onReset) {
  const reset = document.createElement("button");
  reset.type = "button";
  reset.className = "btn btn-quiet btn-icon btn-sm color-row-reset";
  reset.title = "Use inherited color";
  reset.innerHTML = '<span class="icon icon-refresh" aria-hidden="true"></span>';
  reset.addEventListener("click", onReset);
  return reset;
}

class ColorRow {
  value = "";

  constructor(container, id, caption, onChange, options) {
    const { onStart = () => {}, onEnd = () => {}, onReset, onRevert, gradient } = options;
    const { row, label, button, swatch, code } = colorRowMarkup(id);
    Object.assign(this, { element: row, label, button, swatch, code });
    this.reset = onReset ? resetButton(onReset) : null;
    if (this.reset) row.append(this.reset);
    container.append(row);
    button.addEventListener("click", () =>
      openPicker({
        trigger: button,
        caption: this.caption,
        value: this.value,
        onStart,
        onEnd,
        onRevert,
        gradient,
        restore: (next) => {
          if (!gradient) this.update(next);
          onRevert(next);
        },
        change: (next) => {
          this.update(next);
          onChange(next);
        },
      }),
    );
    this.setCaption(caption);
  }

  update(next) {
    this.value = next.toLowerCase();
    this.swatch.style.backgroundColor = this.value;
    this.code.textContent = this.value.slice(1).toUpperCase();
    syncPicker(this.button, this.value);
  }

  // A background: the swatch paints the fill; the value is its start color, and its picker
  // edits the gradient's stops.
  showFill(colors, gradient) {
    this.value = colors.top;
    this.swatch.style.background = cssGradient(colors, gradient);
    this.code.textContent = FILL_NAMES[gradient.kind] || colors.top.slice(1).toUpperCase();
    syncPicker(this.button, this.value);
  }

  setCaption(next) {
    this.caption = next;
    this.label.textContent = next;
    this.button.setAttribute("aria-label", `Edit ${next.toLowerCase()}`);
    this.reset?.setAttribute("aria-label", `Reset ${next.toLowerCase()}`);
  }

  // Rows without a reset button have nothing to mark.
  setOverridden(overridden) {
    if (!this.reset) return;
    this.reset.disabled = !overridden;
    this.element.classList.toggle("is-overridden", overridden);
  }
}

export function colorControl(container, id, caption, onChange, options = {}) {
  return new ColorRow(container, id, caption, onChange, options);
}
