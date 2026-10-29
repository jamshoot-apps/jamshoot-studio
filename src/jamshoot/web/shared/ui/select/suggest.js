// Suggestions under a text field: typing stays free and narrows the whole, scrollable list;
// picking a suggestion fills the field.
import { placeMenu, revealOption } from "./select.js";

class Suggestions {
  active = -1;
  shown = [];

  // `entries` are { value, label }; a typed prefix of either matches.
  constructor(input, entries) {
    Object.assign(this, { input, entries });
    this.list = document.createElement("div");
    this.list.className = "select-menu";
    this.list.id = `${input.id}-suggestions`;
    this.list.popover = "manual";
    this.list.setAttribute("role", "listbox");
    // Last in the form, so field spacing stays as it was; the list is placed by position.
    (input.form || input.parentElement).append(this.list);
    input.setAttribute("role", "combobox");
    input.setAttribute("aria-autocomplete", "list");
    input.setAttribute("aria-controls", this.list.id);
    input.setAttribute("aria-expanded", "false");
    input.addEventListener("input", () => this.show());
    input.addEventListener("focus", () => this.show());
    input.addEventListener("blur", () => this.hide());
    input.addEventListener("keydown", (event) => this.#keydown(event));
  }

  get isOpen() {
    return this.list.matches(":popover-open");
  }

  #matches() {
    const query = this.input.value.trim().toLowerCase();
    const starts = (text) =>
      text
        .toLowerCase()
        .split(/[\s()-]+/)
        .some((word) => word.startsWith(query));
    return this.entries.filter(
      ({ value, label }) => value.toLowerCase() !== query && (starts(value) || starts(label)),
    );
  }

  show() {
    this.shown = this.#matches();
    this.active = -1;
    this.list.replaceChildren(...this.shown.map((entry, index) => this.#option(entry, index)));
    if (!this.shown.length) return this.hide();
    if (!this.isOpen) this.list.showPopover();
    this.list.scrollTop = 0;
    this.input.setAttribute("aria-expanded", "true");
    placeMenu(this.input, this.list);
  }

  hide() {
    if (this.isOpen) this.list.hidePopover();
    this.input.setAttribute("aria-expanded", "false");
    this.input.removeAttribute("aria-activedescendant");
  }

  #option({ value, label }, index) {
    const item = document.createElement("div");
    item.className = "select-option";
    item.id = `${this.list.id}-${index}`;
    item.setAttribute("role", "option");
    item.setAttribute("aria-selected", "false");
    const caption = document.createElement("span");
    caption.textContent = label;
    const detail = document.createElement("span");
    detail.className = "select-detail";
    detail.textContent = value;
    item.append(caption, detail);
    // Keep focus in the field so blur does not close the list before the pick.
    item.addEventListener("pointerdown", (event) => event.preventDefault());
    item.addEventListener("click", () => this.pick(index));
    item.addEventListener("pointermove", () => this.#highlight(index));
    return item;
  }

  #highlight(index) {
    this.active = index;
    for (const [position, item] of [...this.list.children].entries())
      item.classList.toggle("is-active", position === index);
    const item = this.list.children[index];
    if (!item) return;
    this.input.setAttribute("aria-activedescendant", item.id);
    revealOption(this.list, item);
  }

  pick(index) {
    this.input.value = this.shown[index].value;
    this.input.dispatchEvent(new Event("input", { bubbles: true }));
    this.hide();
  }

  // Arrows move through the open list, Enter picks and Escape closes only the list.
  #keydown(event) {
    const action = this.isOpen && this.#keyAction(event.key);
    if (!action) return;
    event.preventDefault();
    if (event.key === "Escape") event.stopPropagation();
    action();
  }

  #keyAction(key) {
    const count = this.shown.length;
    const actions = {
      ArrowDown: () => this.#highlight((this.active + 1) % count),
      ArrowUp: () => this.#highlight((this.active - 1 + count) % count),
      Escape: () => this.hide(),
    };
    if (key === "Enter") return this.active >= 0 ? () => this.pick(this.active) : null;
    return actions[key];
  }
}

export function suggest(input, entries) {
  return new Suggestions(input, entries);
}
