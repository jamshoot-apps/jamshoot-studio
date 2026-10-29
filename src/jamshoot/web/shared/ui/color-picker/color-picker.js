// One reusable, project-agnostic HSV picker dialog shared by every color row; for a
// background it also edits the gradient.

import { dialogBehavior } from "../dialogs/dialogs.js";
import { clamp, hexToHSV, hsvToHex, recentColors, rememberColor } from "./color.js";
import { GradientEditor } from "./gradient-editor.js";

// Static component markup only; project names and colors are assigned as text/properties.
const PICKER_MARKUP = `
    <header class="dialog-heading color-picker-heading"><div><h2 id="picker-title">Color</h2><p data-color-caption></p></div><button type="button" class="btn btn-quiet btn-icon" aria-label="Close color picker" title="Close" data-color-close><span class="icon icon-close" aria-hidden="true"></span></button></header>
    <div class="color-picker-body">
      <div class="color-picker-plane" data-color-plane tabindex="0" role="group" aria-label="Saturation and brightness" aria-describedby="picker-help"><span class="color-picker-cursor" aria-hidden="true"></span></div>
      <p id="picker-help" class="sr-only">Arrow left and right adjust saturation. Arrow up and down adjust brightness. Shift changes by ten percent.</p>
      <label for="picker-hue">Hue</label><div class="color-picker-hue-track"><input id="picker-hue" data-color-hue type="range" min="0" max="360" step="1" class="color-picker-hue"><span class="color-picker-cursor" aria-hidden="true"></span></div>
      <div class="color-picker-channels"><div><label for="picker-saturation">Saturation</label><input id="picker-saturation" data-color-saturation type="number" min="0" max="100" step="any" required></div><div><label for="picker-brightness">Brightness</label><input id="picker-brightness" data-color-brightness type="number" min="0" max="100" step="any" required></div></div>
      <div class="color-picker-hex"><span class="color-picker-preview" aria-hidden="true"></span><div><label for="picker-hex">HEX</label><input id="picker-hex" data-color-hex type="text" required pattern="#[0-9a-fA-F]{6}" maxlength="7" spellcheck="false" autocomplete="off"></div></div>
      <section data-color-swatch-section><h3>Recent colors</h3><div class="color-picker-swatches" data-color-swatches></div></section>
      <div class="color-picker-actions"><button type="button" data-color-revert class="btn">Revert</button><button type="button" data-color-done class="btn btn-primary">Done</button></div>
    </div>`;
// Arrow keys on the plane: which channel moves and in which direction.
const PLANE_KEYS = {
  ArrowLeft: ["s", -1],
  ArrowRight: ["s", 1],
  ArrowUp: ["v", 1],
  ArrowDown: ["v", -1],
};

function swatchButton(color, onPick) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = "color-picker-swatch";
  button.style.backgroundColor = color;
  button.setAttribute("aria-label", `Recent color ${color}`);
  button.title = `Recent color · ${color}`;
  button.addEventListener("click", () => onPick(color));
  return button;
}

// Spacing tokens are rem lengths; positions are pixels.
function tokenPixels(style, name) {
  const rem = parseFloat(getComputedStyle(document.documentElement).fontSize);
  return parseFloat(style.getPropertyValue(name)) * rem;
}

// One dialog serves every color row. An owner is the row that opened it; one opening is one
// edit session, ended exactly once by Done, Close, Escape or the backdrop.
class ColorPicker {
  owner = null;
  value = "";
  original = "";
  hsv = { h: 0, s: 0, v: 0 };
  edited = false;
  sessionEnded = true;

  constructor() {
    const dialog = document.createElement("dialog");
    dialog.className = "dialog color-picker-dialog";
    dialog.innerHTML = PICKER_MARKUP;
    dialog.setAttribute("aria-labelledby", "picker-title");
    document.body.append(dialog);
    this.dialog = dialog;
    dialogBehavior(dialog, () => this.#close());
    this.plane = this.#find("plane");
    this.hex = this.#find("hex");
    this.hue = this.#find("hue");
    this.saturation = this.#find("saturation");
    this.brightness = this.#find("brightness");
    this.gradient = new GradientEditor(dialog.querySelector(".color-picker-body"), {
      onSelect: (color) => this.#show(color),
      onEdit: () => {
        this.edited = true;
        this.#paint();
      },
    });
    this.#listenInputs();
    this.#listenPlane();
    this.#listenDialog();
    window.addEventListener("resize", () => this.#place());
  }

  #find(name) {
    return this.dialog.querySelector(`[data-color-${name}]`);
  }

  #paint() {
    const { hsv, plane, value } = this;
    this.hue.value = hsv.h;
    this.saturation.value = Math.round(hsv.s * 100) / 100;
    this.brightness.value = Math.round(hsv.v * 100) / 100;
    this.hex.value = value;
    plane.style.setProperty("--picker-color", hsvToHex(hsv.h, 100, 100));
    plane.style.setProperty("--picker-x", `${hsv.s}%`);
    plane.style.setProperty("--picker-y", `${100 - hsv.v}%`);
    this.hue.parentElement.style.setProperty("--picker-hue", String(hsv.h / 360));
    plane.setAttribute(
      "aria-label",
      `Saturation ${Math.round(hsv.s)}%, brightness ${Math.round(hsv.v)}%`,
    );
    this.dialog.querySelector(".color-picker-preview").style.backgroundColor = value;
    this.#find("revert").disabled = !this.edited;
  }

  #show(value) {
    this.value = value;
    this.hsv = hexToHSV(value);
    this.#paint();
  }

  #apply(next, fromHSV = false) {
    const changed = next !== this.value;
    this.value = next;
    if (!fromHSV) this.hsv = hexToHSV(next);
    if (changed) this.edited = true;
    this.#paint();
    if (changed) this.#send(next);
  }

  // A background's picker colors the selected gradient stop; other rows take the color.
  #send(next) {
    if (this.owner.gradient) this.gradient.setColor(next);
    else this.owner.change(next);
  }

  #applyHSV() {
    const { h, s, v } = this.hsv;
    this.#apply(hsvToHex(h, s, v), true);
  }

  #listenInputs() {
    this.hue.addEventListener("input", () => {
      this.hsv.h = this.hue.valueAsNumber;
      this.#applyHSV();
    });
    for (const [input, key] of [
      [this.saturation, "s"],
      [this.brightness, "v"],
    ])
      input.addEventListener("change", () => {
        if (!input.reportValidity()) return;
        this.hsv[key] = input.valueAsNumber;
        this.#applyHSV();
      });
    this.hex.addEventListener("change", () => {
      if (this.hex.reportValidity()) this.#apply(this.hex.value.toLowerCase());
    });
  }

  #point(event) {
    const rect = this.plane.getBoundingClientRect();
    this.hsv.s = clamp(((event.clientX - rect.left) / rect.width) * 100, 0, 100);
    this.hsv.v = clamp(100 - ((event.clientY - rect.top) / rect.height) * 100, 0, 100);
    this.#applyHSV();
  }

  #nudge(event) {
    const move = PLANE_KEYS[event.key];
    if (!move) return;
    event.preventDefault();
    const [key, direction] = move;
    this.hsv[key] = clamp(this.hsv[key] + direction * (event.shiftKey ? 10 : 1), 0, 100);
    this.#applyHSV();
  }

  #listenPlane() {
    const { plane } = this;
    plane.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      plane.setPointerCapture(event.pointerId);
      plane.focus();
      this.#point(event);
    });
    plane.addEventListener("pointermove", (event) => {
      if (plane.hasPointerCapture(event.pointerId)) this.#point(event);
    });
    plane.addEventListener("pointerup", (event) => {
      if (plane.hasPointerCapture(event.pointerId)) plane.releasePointerCapture(event.pointerId);
    });
    plane.addEventListener("keydown", (event) => this.#nudge(event));
  }

  #finish() {
    if (this.sessionEnded) return;
    this.sessionEnded = true;
    if (this.edited) rememberColor(this.value);
    this.owner.onEnd();
  }

  #returnFocus() {
    this.owner?.trigger.focus({ preventScroll: true });
  }

  #close() {
    this.dialog.close();
    this.#finish();
    this.#returnFocus();
  }

  // An owner with onRevert restores its inherited value itself; others get the original back.
  #revert() {
    if (this.owner.onRevert) {
      this.owner.restore(this.original);
      this.gradient.attach(this.owner.gradient ?? null);
      this.#show(this.gradient.selectedColor ?? this.original);
    } else this.#apply(this.original);
    this.edited = false;
    this.#paint();
  }

  #listenDialog() {
    const { dialog } = this;
    this.#find("close").addEventListener("click", () => this.#close());
    this.#find("done").addEventListener("click", () => this.#close());
    this.#find("revert").addEventListener("click", () => this.#revert());
    dialog.addEventListener("close", () => {
      if (!dialog.open) this.#finish();
    });
    dialog.addEventListener("cancel", () => {
      this.#finish();
      this.#returnFocus();
    });
  }

  // Beside the triggering row, left of it when there is room; narrow screens use a bottom sheet.
  #place() {
    const { dialog } = this;
    if (!dialog.open) return;
    const rect = this.owner.trigger.getBoundingClientRect(),
      tokens = getComputedStyle(dialog);
    const gap = tokenPixels(tokens, "--ds-space-xs"),
      margin = tokenPixels(tokens, "--ds-space-sm");
    const width = dialog.offsetWidth,
      height = dialog.offsetHeight;
    const before = rect.left - width - gap;
    const left = before >= margin ? before : rect.right + gap;
    const maxLeft = Math.max(margin, innerWidth - width - margin),
      maxTop = Math.max(margin, innerHeight - height - margin);
    dialog.style.setProperty("--picker-left", `${clamp(left, margin, maxLeft)}px`);
    dialog.style.setProperty("--picker-top", `${clamp(rect.top, margin, maxTop)}px`);
  }

  #renderSwatches() {
    const pick = (color) => this.#apply(color);
    this.#find("swatches").replaceChildren(
      ...recentColors().map((color) => swatchButton(color, pick)),
    );
    this.#find("swatch-section").hidden = !this.#find("swatches").childElementCount;
  }

  open(context) {
    this.#finish();
    this.owner = context;
    this.sessionEnded = false;
    this.edited = false;
    this.original = context.value;
    this.gradient.attach(context.gradient ?? null);
    this.#show(this.gradient.selectedColor ?? context.value);
    context.onStart();
    this.#find("caption").textContent = context.caption;
    this.#renderSwatches();
    this.dialog.showModal();
    this.#place();
  }

  // Keeps an open picker in step when its owner's value changes elsewhere, such as Undo.
  // A background shows its selected stop.
  update(trigger, next) {
    if (!this.#owns(trigger)) return;
    const shown = this.#shownColor(next);
    if (shown !== this.value) this.#show(shown);
  }

  #owns(trigger) {
    return this.dialog.open && this.owner?.trigger === trigger;
  }

  #shownColor(next) {
    if (this.owner.gradient) this.gradient.sync();
    return this.gradient.selectedColor ?? next;
  }
}

let sharedPicker;

export function openPicker(context) {
  sharedPicker ??= new ColorPicker();
  sharedPicker.open(context);
}

export function syncPicker(trigger, value) {
  sharedPicker?.update(trigger, value);
}
