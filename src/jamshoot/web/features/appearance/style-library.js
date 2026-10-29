// A saved style library in the Project dialog: create, rename, edit, duplicate and delete.
// Its owner draws each entry's preview and the fields that edit its values.

import { LIBRARIES } from "../../shared/model/project.js";
import { button } from "../../shared/ui/button/button.js";

const slideCount = (usage) => new Set(usage.map((item) => item.slide)).size;

export function usageLabel(usage) {
  const slides = slideCount(usage);
  return slides ? `Used on ${slides} ${slides === 1 ? "slide" : "slides"}` : "Not used";
}

function iconButton(label, icon, hint, variant = "quiet") {
  return button({ label, icon, variant, iconOnly: true, title: hint });
}

// Slides keep a deleted entry's values, so only an entry in use asks first.
function confirmDelete(item, usage, kept) {
  const slides = slideCount(usage);
  if (!slides) return true;
  const keep = slides === 1 ? "slide keeps its" : "slides keep their";
  return window.confirm(`Delete “${item.name}”? ${slides} ${keep} current ${kept}.`);
}

// `kind` names a model library; `idPrefix` prefixes element ids and each row's data attribute;
// `elements` holds the list, its add button and count; `text` the empty and kept wording.
// Hooks: `preview(item)` draws a row's mark, `newValues()` gives a new entry (its value groups) and
// `showValues(item)` fills the fields of the open entry.
export class StyleLibrary {
  editing = null;
  panel = document.createElement("div");
  nameInput = document.createElement("input");

  constructor({ kind, idPrefix, elements, text }, { getState, changed, ...hooks }) {
    Object.assign(this, { kind, idPrefix, text, getState, changed, hooks });
    Object.assign(this, elements);
    this.noun = LIBRARIES[kind].noun.toLowerCase();
    this.fields = this.#buildPanel();
    this.nameInput.addEventListener("change", () => this.#rename());
    this.add.addEventListener("click", () => this.#create());
  }

  get styles() {
    return this.getState().project[LIBRARIES[this.kind].list] || [];
  }

  get current() {
    return this.styles.find((item) => item.id === this.editing);
  }

  get #full() {
    return this.getState().isFull(LIBRARIES[this.kind].list);
  }

  #buildPanel() {
    const { panel, nameInput, idPrefix } = this;
    const label = document.createElement("label"),
      fields = document.createElement("div");
    panel.className = "palette-editor";
    panel.id = `${idPrefix}-editor`;
    label.htmlFor = `${idPrefix}-name`;
    label.textContent = `${LIBRARIES[this.kind].noun} name`;
    nameInput.id = `${idPrefix}-name`;
    nameInput.maxLength = 200;
    nameInput.required = true;
    nameInput.autocomplete = "off";
    fields.className = "palette-editor-colors";
    panel.append(label, nameInput, fields);
    return fields;
  }

  setValue(key, value) {
    const current = this.current;
    if (!current) return;
    const [group] = LIBRARIES[this.kind].groups;
    this.getState().updateSavedStyle(this.kind, current.id, current.name, {
      [group]: { ...current[group], [key]: value },
    });
    this.changed(`Edit ${this.noun}`);
  }

  // An empty name restores the saved one instead of failing validation.
  #rename() {
    const current = this.current;
    if (!current) return;
    if (!this.nameInput.value.trim()) {
      this.nameInput.value = current.name;
      return;
    }
    this.getState().updateSavedStyle(this.kind, current.id, this.nameInput.value);
    this.changed(`Rename ${this.noun}`);
  }

  #open(id, label) {
    this.editing = id;
    this.changed(label);
    this.nameInput.focus();
  }

  #create() {
    const state = this.getState();
    const id = state.addSavedStyle(
      this.kind,
      state.nextStyleName(this.kind),
      this.hooks.newValues(),
    );
    this.#open(id, `New ${this.noun}`);
    this.nameInput.select();
  }

  #toggle(id, edit) {
    this.editing = this.editing === id ? null : id;
    this.update();
    (this.editing ? this.nameInput : edit).focus();
  }

  #remove(item, usage) {
    if (!confirmDelete(item, usage, this.text.kept)) return;
    if (this.editing === item.id) this.editing = null;
    this.getState().deleteSavedStyle(this.kind, item.id);
    this.changed(`Delete ${this.noun}`);
    (this.list.querySelector("button") || this.add).focus();
  }

  #actions(item, usage) {
    const open = this.editing === item.id,
      noun = this.noun;
    const actions = document.createElement("div");
    actions.className = "palette-row-actions";
    const edit = open
      ? iconButton(`Close ${item.name}`, "check", "Done editing")
      : iconButton(`Edit ${item.name}`, "edit", `Edit ${noun}`);
    edit.setAttribute("aria-expanded", String(open));
    edit.addEventListener("click", () => this.#toggle(item.id, edit));
    const duplicate = iconButton(`Duplicate ${item.name}`, "copy", `Duplicate ${noun}`);
    duplicate.disabled = this.#full;
    duplicate.addEventListener("click", () =>
      this.#open(this.getState().duplicateSavedStyle(this.kind, item.id), `Duplicate ${noun}`),
    );
    const remove = iconButton(`Delete ${item.name}`, "trash", `Delete ${noun}`, "danger");
    remove.addEventListener("click", () => this.#remove(item, usage));
    actions.append(edit, duplicate, remove);
    return actions;
  }

  #row(item, usage) {
    const element = document.createElement("li"),
      main = document.createElement("div");
    const text = document.createElement("span"),
      label = document.createElement("strong"),
      meta = document.createElement("small");
    element.className = "palette-row";
    element.dataset[this.idPrefix] = item.id;
    main.className = "palette-row-main";
    label.textContent = item.name;
    meta.className = "detail";
    meta.textContent = usageLabel(usage);
    text.append(label, meta);
    main.append(this.hooks.preview(item), text, this.#actions(item, usage));
    element.append(main);
    return element;
  }

  // Rows are rebuilt on every update; the returned callback puts focus back afterwards.
  #keepFocus() {
    const active = document.activeElement;
    if (this.panel.contains(active))
      return () => active.isConnected && active.focus({ preventScroll: true });
    const row = active.closest(`#${this.list.id} [data-${this.idPrefix}]`);
    if (!row) return () => {};
    const id = row.dataset[this.idPrefix],
      hint = active.title;
    return () =>
      [...this.list.querySelectorAll(`[data-${this.idPrefix}="${id}"] button`)]
        .find((item) => item.title === hint)
        ?.focus({ preventScroll: true });
  }

  #showPanel() {
    const current = this.current;
    if (!current) return;
    this.list.querySelector(`[data-${this.idPrefix}="${current.id}"]`).append(this.panel);
    if (document.activeElement !== this.nameInput) this.nameInput.value = current.name;
    this.hooks.showValues(current);
  }

  #emptyRow() {
    const empty = document.createElement("li");
    empty.className = "palette-empty hint";
    empty.textContent = this.text.empty;
    return empty;
  }

  update() {
    const state = this.getState(),
      styles = this.styles;
    if (!this.current) this.editing = null;
    const restoreFocus = this.#keepFocus();
    const rows = styles.map((item) => this.#row(item, state.savedStyleUsage(this.kind, item.id)));
    this.list.replaceChildren(...(rows.length ? rows : [this.#emptyRow()]));
    this.#showPanel();
    restoreFocus();
    this.count.textContent = String(styles.length);
    this.add.disabled = this.#full;
  }

  reset() {
    this.editing = null;
  }
}
