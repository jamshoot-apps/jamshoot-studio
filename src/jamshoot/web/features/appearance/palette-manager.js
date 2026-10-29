// Project → Colors: every palette as a card and an editor for the chosen one. Edits apply at
// once and are undoable; starter palettes are read-only until customized into a copy.

import { $ } from "../../shared/lib/dom.js";
import { title } from "../../shared/lib/text.js";
import { paletteEntry } from "../../shared/model/project.js";
import { cssGradient } from "../../shared/ui/color-picker/color.js";
import { colorControl } from "../../shared/ui/color-picker/color-row.js";
import { backgroundControl, COLOR_LABELS } from "./background.js";
import { paletteSections, renderPaletteCards } from "./palettes.js";
import { usageLabel } from "./style-library.js";

class PaletteManager {
  selected = "";

  // `changed(label)` redraws and records an edit; `editSession` groups a picker's edits.
  constructor({ schema, appearance, getState, changed, editSession = {} }) {
    Object.assign(this, { appearance, getState, changed, editSession });
    const fields = $("palette-fields");
    let original;
    this.background = backgroundControl(fields, "palette-background", {
      schema,
      write: (key, value) => this.#edit("colors", key, value),
      writeGradient: (key, value) => this.#edit("gradient", key, value),
      editSession: {
        onStart: () => {
          original = { colors: { ...this.saved?.colors }, gradient: { ...this.saved?.gradient } };
          editSession.onStart?.("Edit palette background");
        },
        onEnd: () => editSession.onEnd?.(),
      },
      onRevert: () => this.#write(original, "Edit palette background"),
    });
    this.colors = {};
    for (const key of Object.keys(COLOR_LABELS)) this.colors[key] = this.#colorRow(key, fields);
    this.#listen();
  }

  #listen() {
    $("palette-list").addEventListener("change", (event) => this.select(event.target.value));
    $("new-palette").addEventListener("click", () => this.#create());
    $("palette-name").addEventListener("change", () => this.#rename());
    $("palette-customize").addEventListener("click", () => this.#customize());
    $("palette-duplicate").addEventListener("click", () => this.#duplicate());
    $("palette-delete").addEventListener("click", () => this.#delete());
    $("palette-make-default").addEventListener("click", () => {
      this.getState().setPalette("project", this.selected);
      this.changed("Use palette as project default");
    });
    $("palette-apply").addEventListener("click", () => {
      this.getState().setPalette("slide", this.selected);
      this.changed("Use palette on slide");
    });
  }

  // The chosen project palette, or null for a starter.
  get saved() {
    const id = this.selected.startsWith("style:") ? this.selected.slice(6) : null;
    return this.getState().project.colorStyles?.find((style) => style.id === id) || null;
  }

  // The chosen palette as `{ name, colors, gradient }`, gradient without defaults.
  get #current() {
    const saved = this.saved;
    if (saved) return saved;
    const id = this.selected.slice("starter:".length);
    return { name: title(id), colors: this.appearance.starterPalettes[id] };
  }

  #valid(value) {
    if (value.startsWith("starter:"))
      return Object.hasOwn(this.appearance.starterPalettes, value.slice("starter:".length));
    return value.startsWith("style:") && Boolean(this.saved);
  }

  select(value) {
    this.selected = value;
    this.update();
  }

  #write(entry, label) {
    const saved = this.saved;
    if (!saved) return;
    this.getState().updateSavedStyle("palette", saved.id, saved.name, entry);
    this.changed(label);
  }

  #edit(group, key, value) {
    const saved = this.saved;
    if (!saved) return;
    const label = group === "colors" ? "Edit palette color" : "Edit palette gradient";
    this.#write({ [group]: { ...saved[group], [key]: value } }, label);
  }

  #colorRow(key, container, onChange = (value) => this.#edit("colors", key, value)) {
    let original;
    return colorControl(container, `palette-color-${key}`, COLOR_LABELS[key], onChange, {
      onStart: () => {
        original = this.saved?.colors[key];
        this.editSession.onStart?.("Edit palette color");
      },
      onEnd: () => this.editSession.onEnd?.(),
      onRevert: () => this.#edit("colors", key, original),
    });
  }

  #add(name, entry, label) {
    const id = this.getState().addSavedStyle("palette", name, entry);
    this.selected = `style:${id}`;
    this.changed(label);
    $("palette-name").focus();
    $("palette-name").select();
  }

  // A new palette starts from the project default, so it is never blank.
  #create() {
    const state = this.getState();
    const entry = paletteEntry(this.appearance, state.defaultStyle);
    this.#add(state.nextStyleName("palette"), entry, "New palette");
  }

  #customize() {
    const { name, colors } = this.#current;
    this.#add(name, { colors }, "Customize palette");
  }

  #duplicate() {
    const copy = this.getState().duplicateSavedStyle("palette", this.saved.id);
    this.selected = `style:${copy}`;
    this.changed("Duplicate palette");
  }

  // A blank name restores the current one.
  #rename() {
    const input = $("palette-name");
    if (!input.value.trim()) {
      input.value = this.#current.name;
      return;
    }
    this.getState().updateSavedStyle("palette", this.saved.id, input.value);
    this.changed("Rename palette");
  }

  #delete() {
    const state = this.getState(),
      saved = this.saved;
    const slides = new Set(state.savedStyleUsage("palette", saved.id).map((use) => use.slide));
    const keep = slides.size === 1 ? "slide keeps its" : "slides keep their";
    if (slides.size && !window.confirm(`Delete “${saved.name}”? ${slides.size} ${keep} colors.`))
      return;
    state.deleteSavedStyle("palette", saved.id);
    this.selected = "";
    this.changed("Delete palette");
    $("new-palette").focus();
  }

  #usage(isDefault) {
    const saved = this.saved;
    const parts = [];
    if (isDefault) parts.push("Project default");
    if (saved) parts.push(usageLabel(this.getState().savedStyleUsage("palette", saved.id)));
    else parts.push("Starter palette. Customize it to edit a copy");
    return `${parts.join(" · ")}.`;
  }

  #preview(colors, gradient) {
    const preview = $("palette-preview");
    preview.style.background = cssGradient(colors, gradient);
    preview.querySelector("strong").style.color = colors.text;
    preview.querySelector("span").style.color = colors.muted;
    preview.querySelector("i").style.background = colors.accent;
  }

  update() {
    const state = this.getState(),
      defaultValue = state.paletteValue("project");
    this.#updateList(state, defaultValue);
    const { name, colors, gradient: own = {} } = this.#current,
      saved = this.saved;
    const gradient = { ...this.appearance.gradientDefaults, ...own };
    for (const [key, control] of Object.entries(this.colors)) control.update(colors[key]);
    this.background.update(colors, gradient);
    this.#preview(colors, gradient);
    if (document.activeElement !== $("palette-name")) $("palette-name").value = name;
    $("palette-name").disabled = !saved;
    $("palette-fields").disabled = !saved;
    $("palette-usage").textContent = this.#usage(this.selected === defaultValue);
    $("palette-customize").hidden = Boolean(saved);
    $("palette-duplicate").hidden = !saved;
    $("palette-delete").hidden = !saved;
    $("palette-make-default").disabled = this.selected === defaultValue;
    $("palette-apply").disabled = state.paletteValue("slide") === this.selected;
    for (const id of ["palette-customize", "palette-duplicate"])
      $(id).disabled = state.isFull("colorStyles");
  }

  #updateList(state, defaultValue) {
    if (!this.#valid(this.selected)) this.selected = defaultValue;
    renderPaletteCards($("palette-list"), paletteSections(state, this.appearance), this.selected);
    $("palette-count").textContent = String(state.project.colorStyles?.length || 0);
    $("new-palette").disabled = state.isFull("colorStyles");
  }
}

export function paletteManager(context) {
  return new PaletteManager(context);
}
