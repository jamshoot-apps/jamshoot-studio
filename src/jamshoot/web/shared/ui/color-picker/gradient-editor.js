// The gradient part of the color picker: fill type, stops on a bar and in a list, and the
// fill's geometry. Click the bar to add a stop; drag a stop anywhere along it, past others
// or away from an end, where its color then fills solid. The picker edits the selected stop.

import { button } from "../button/button.js";
import { rangeControl } from "../range-control/range-control.js";
import { enhanceSelect } from "../select/select.js";
import { colorAt, cssStops, gradientStops } from "./color.js";

const KINDS = { linear: "Linear", radial: "Radial", solid: "Solid" };
const CAPTIONS = {
  angle: "Angle (°)",
  centerX: "Center X (%)",
  centerY: "Center Y (%)",
  radius: "Size (%)",
};
// The geometry fields each fill shows.
const FIELDS = { linear: ["angle"], radial: ["centerX", "centerY", "radius"], solid: [] };
const KEY_STEPS = { ArrowLeft: -1, ArrowRight: 1 };
const REMOVE_KEYS = new Set(["Delete", "Backspace"]);

const clampPosition = (value) => Math.round(Math.min(100, Math.max(0, value)) * 10) / 10;
const byPosition = (stops) => [...stops].sort((a, b) => a.position - b.position);

function element(tag, className, text = "") {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

// `onSelect(color)` shows a stop's color in the picker; `onEdit()` marks the session edited.
export class GradientEditor {
  source = null;
  stops = [];
  selected = null;
  limits = { minItems: 2, maxItems: 8 };

  constructor(container, { onSelect, onEdit }) {
    Object.assign(this, { onSelect, onEdit });
    this.element = element("section", "gradient-editor");
    this.element.setAttribute("aria-label", "Gradient");
    this.element.hidden = true;
    this.#head();
    this.#bar();
    this.#list();
    this.fields = element("div", "gradient-fields");
    this.element.append(this.fields);
    container.prepend(this.element);
  }

  #head() {
    const head = element("div", "gradient-head");
    this.kind = document.createElement("select");
    this.kind.id = "picker-fill";
    this.kind.setAttribute("aria-label", "Fill");
    this.kind.append(...Object.entries(KINDS).map(([value, label]) => new Option(label, value)));
    this.kind.addEventListener("change", () => this.#set("kind", this.kind.value));
    this.swap = button({
      label: "Reverse stops",
      icon: "swap",
      variant: "quiet",
      size: "sm",
      iconOnly: true,
      onClick: () => this.#reverse(),
    });
    this.rotate = button({
      label: "Rotate 90°",
      icon: "refresh",
      variant: "quiet",
      size: "sm",
      iconOnly: true,
      onClick: () => this.#set("angle", (this.source.read().gradient.angle + 90) % 360),
    });
    head.append(this.kind, this.swap, this.rotate);
    this.element.append(head);
    enhanceSelect(this.kind);
  }

  // Pressing the bar outside a stop adds one there, in the color the gradient has there.
  #bar() {
    this.bar = element("div", "gradient-bar");
    this.bar.setAttribute("role", "group");
    this.bar.setAttribute("aria-label", "Gradient stops; click to add one");
    this.bar.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 || event.target !== this.bar) return;
      this.add(this.#positionAt(event));
      this.handles.get(this.selected)?.focus();
    });
    this.handles = new Map();
    this.element.append(this.bar);
  }

  #list() {
    const heading = element("div", "gradient-stops-heading");
    this.addButton = button({
      label: "Add stop",
      icon: "add",
      variant: "quiet",
      size: "sm",
      iconOnly: true,
      onClick: () => this.add(this.#freePosition()),
    });
    heading.append(element("h4", "", "Stops"), this.addButton);
    this.rows = element("ul", "gradient-stops");
    this.element.append(heading, this.rows);
  }

  #positionAt(event) {
    const rect = this.bar.getBoundingClientRect();
    return clampPosition(((event.clientX - rect.left) / rect.width) * 100);
  }

  // The middle of the widest gap between stops, where a new stop is easiest to see.
  #freePosition() {
    const ordered = byPosition(this.stops);
    let best = { gap: -1, position: 50 };
    for (const [index, stop] of ordered.slice(0, -1).entries()) {
      const gap = ordered[index + 1].position - stop.position;
      if (gap > best.gap) best = { gap, position: stop.position + gap / 2 };
    }
    return clampPosition(best.position);
  }

  #set(key, value) {
    this.onEdit();
    this.source.set(key, value);
    this.sync();
  }

  // Writes the working stops; their order in the project follows their positions.
  #commit() {
    this.onEdit();
    this.source.setStops(
      byPosition(this.stops).map(({ color, position }) => ({ color, position })),
    );
    this.#render();
  }

  #reverse() {
    for (const stop of this.stops) stop.position = clampPosition(100 - stop.position);
    this.#commit();
  }

  add(position) {
    if (this.stops.length >= this.limits.maxItems) return;
    const stop = { color: colorAt(byPosition(this.stops), position), position };
    this.stops.push(stop);
    this.selected = stop;
    this.onSelect(stop.color);
    this.#commit();
  }

  remove(stop) {
    if (this.stops.length <= this.limits.minItems) return;
    const ordered = byPosition(this.stops),
      index = ordered.indexOf(stop);
    this.stops = this.stops.filter((other) => other !== stop);
    if (this.selected === stop) this.select(ordered[index + 1] || ordered[index - 1], false);
    this.#commit();
  }

  move(stop, position) {
    if (stop.position === position) return;
    stop.position = position;
    this.#commit();
  }

  // The picker changed the selected stop's color.
  setColor(color) {
    if (!this.selected || this.selected.color === color) return;
    this.selected.color = color;
    this.#commit();
  }

  get selectedColor() {
    return this.selected?.color;
  }

  select(stop, render = true) {
    this.selected = stop;
    this.onSelect(stop.color);
    if (render) this.#render();
  }

  // Sliders and numbers built once per picker from the owner's schema limits.
  #buildFields(limits) {
    if (this.inputs) return;
    this.inputs = {};
    for (const [key, caption] of Object.entries(CAPTIONS))
      this.inputs[key] = rangeControl(this.fields, `picker-${key}`, caption, limits[key], (value) =>
        this.#set(key, value),
      );
    Object.assign(this.limits, limits.stops);
  }

  // `source` is `{ limits, read(), set(key, value), setStops(stops) }`, or null for a plain
  // color.
  attach(source) {
    this.source = source;
    this.element.hidden = !source;
    if (!source) return;
    this.#buildFields(source.limits);
    this.selected = null;
    this.sync();
  }

  // Re-reads the stops after a change elsewhere, such as Undo, keeping the selected place.
  // Stops this editor just wrote stay the same objects, so a drag keeps its handle.
  sync() {
    if (!this.source) return;
    const { colors, gradient } = this.source.read();
    const read = gradientStops(colors, gradient);
    if (this.#sameStops(read)) {
      this.#render();
      return;
    }
    const index = this.selected ? byPosition(this.stops).indexOf(this.selected) : 0;
    this.stops = read.map((stop) => ({ ...stop }));
    this.selected = this.stops[Math.min(Math.max(index, 0), this.stops.length - 1)];
    this.#render();
  }

  #sameStops(read) {
    const plain = (stops) => JSON.stringify(stops.map(({ color, position }) => [color, position]));
    return this.stops.length && plain(read) === plain(byPosition(this.stops));
  }

  #render() {
    const { gradient } = this.source.read(),
      solid = gradient.kind === "solid",
      ordered = byPosition(this.stops);
    this.kind.value = gradient.kind;
    this.kind.menu.refresh();
    for (const node of [this.bar, this.rows, this.rows.previousElementSibling]) node.hidden = solid;
    this.swap.disabled = solid;
    this.rotate.hidden = gradient.kind !== "linear";
    this.addButton.disabled = this.stops.length >= this.limits.maxItems;
    this.bar.style.background = `linear-gradient(90deg, ${cssStops(ordered)})`;
    this.#renderHandles();
    this.rows.replaceChildren(...ordered.map((stop, index) => this.#row(stop, index)));
    for (const [key, control] of Object.entries(this.inputs)) {
      control.element.hidden = !FIELDS[gradient.kind].includes(key);
      if (!control.element.contains(document.activeElement)) control.update(gradient[key]);
    }
  }

  // Handles are kept across renders, so a drag and keyboard focus survive each edit.
  #renderHandles() {
    this.#dropHandles();
    for (const stop of this.stops) {
      const handle = this.handles.get(stop) || this.#handle(stop);
      handle.style.left = `${stop.position}%`;
      handle.style.backgroundColor = stop.color;
      handle.setAttribute("aria-pressed", String(stop === this.selected));
      handle.setAttribute("aria-label", `Stop ${stop.color} at ${stop.position}%`);
    }
  }

  // Removes the handles of stops that are gone.
  #dropHandles() {
    for (const [stop, handle] of this.handles) {
      if (this.stops.includes(stop)) continue;
      handle.remove();
      this.handles.delete(stop);
    }
  }

  #handle(stop) {
    const handle = element("button", "gradient-stop");
    handle.type = "button";
    handle.addEventListener("pointerdown", (event) => {
      if (event.button !== 0) return;
      handle.setPointerCapture(event.pointerId);
      this.select(stop);
    });
    handle.addEventListener("pointermove", (event) => {
      if (handle.hasPointerCapture(event.pointerId)) this.move(stop, this.#positionAt(event));
    });
    handle.addEventListener("keydown", (event) => this.#key(event, stop));
    handle.addEventListener("click", () => this.select(stop));
    this.handles.set(stop, handle);
    this.bar.append(handle);
    return handle;
  }

  // Arrows move a stop (Shift by 10%); Delete and Backspace remove it.
  #key(event, stop) {
    const action = this.#keyAction(event, stop);
    if (!action) return;
    event.preventDefault();
    action();
  }

  #keyAction(event, stop) {
    const step = KEY_STEPS[event.key];
    if (step)
      return () => this.move(stop, clampPosition(stop.position + step * (event.shiftKey ? 10 : 1)));
    if (!REMOVE_KEYS.has(event.key)) return null;
    return () => {
      this.remove(stop);
      this.handles.get(this.selected)?.focus();
    };
  }

  #row(stop, index) {
    const row = element("li", "gradient-stop-row"),
      swatch = element("button", "gradient-stop-swatch"),
      position = document.createElement("input");
    row.classList.toggle("is-selected", stop === this.selected);
    swatch.type = "button";
    swatch.style.backgroundColor = stop.color;
    swatch.setAttribute("aria-label", `Edit stop ${index + 1} color`);
    swatch.setAttribute("aria-pressed", String(stop === this.selected));
    swatch.addEventListener("click", () => this.select(stop));
    Object.assign(position, {
      type: "number",
      min: 0,
      max: 100,
      step: "any",
      value: stop.position,
    });
    position.setAttribute("aria-label", `Stop ${index + 1} position (%)`);
    position.addEventListener("change", () => {
      if (position.reportValidity()) this.move(stop, clampPosition(position.valueAsNumber));
    });
    const remove = button({
      label: `Remove stop ${index + 1}`,
      icon: "close",
      variant: "quiet",
      size: "sm",
      iconOnly: true,
      onClick: () => this.remove(stop),
    });
    remove.disabled = this.stops.length <= this.limits.minItems;
    row.append(swatch, element("code", "gradient-stop-code", stop.color.slice(1).toUpperCase()));
    row.append(position, element("span", "gradient-stop-unit", "%"), remove);
    return row;
  }
}
