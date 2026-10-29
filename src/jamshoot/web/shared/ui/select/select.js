// Styled single-select over a native <select>, which keeps the value, change events and forms.
// With `data-menu` it is an action menu instead: the trigger always reads its placeholder,
// such as "Add size", and each pick fires one change event, then the value clears.
// An option's `data-trigger` is what the trigger shows for it, such as "Mac · 1280 × 800".
import { icon } from "../icon/icon.js";

const valueDescriptor = Object.getOwnPropertyDescriptor(HTMLSelectElement.prototype, "value");
const GAP = 4;
const MARGIN = 8;
const ROOM_BELOW = 240;
const selectedText = (option = { dataset: {} }) => option.dataset.trigger || option.textContent;
const available = (option) => option && !option.disabled;
// One menu is open at a time; window listeners follow it, so menus redrawn with their
// list leave no listeners behind.
let openMenu = null;
addEventListener("resize", () => openMenu?.place());
document.addEventListener(
  "scroll",
  (event) => {
    if (openMenu && !openMenu.list.contains(event.target)) openMenu.close(false);
  },
  true,
);

// Below `anchor` when the menu fits there, otherwise above it, always inside the viewport.
// Scrolls only the menu to `item`; scrollIntoView would also scroll the panel behind it.
export function revealOption(list, item) {
  if (item.offsetTop < list.scrollTop) list.scrollTop = item.offsetTop - GAP;
  else if (item.offsetTop + item.offsetHeight > list.scrollTop + list.clientHeight)
    list.scrollTop = item.offsetTop + item.offsetHeight - list.clientHeight + GAP;
}

export function placeMenu(anchor, list) {
  const rect = anchor.getBoundingClientRect();
  list.style.minWidth = `${rect.width}px`;
  const height = list.offsetHeight;
  const below = innerHeight - rect.bottom - MARGIN;
  const fitsBelow = below >= Math.min(height, ROOM_BELOW) || rect.top < below;
  const top = fitsBelow ? rect.bottom + GAP : Math.max(MARGIN, rect.top - GAP - height);
  const lowest = innerHeight - MARGIN - Math.min(height, innerHeight - 2 * MARGIN);
  list.style.top = `${Math.min(top, lowest)}px`;
  list.style.left = `${Math.max(MARGIN, Math.min(rect.left, innerWidth - list.offsetWidth - MARGIN))}px`;
}

function element(tag, className) {
  const node = document.createElement(tag);
  node.className = className;
  return node;
}

// An option's label and, with `data-detail`, a short muted status after it, such as "Missing".
// `data-action="add"` marks a command such as "Add language…", drawn with a plus.
function optionText(option) {
  const caption = document.createElement("span");
  caption.textContent = option.textContent;
  const parts = option.dataset.action ? [icon("add"), caption] : [caption];
  if (!option.dataset.detail) return parts;
  const detail = element("span", "select-detail");
  detail.textContent = option.dataset.detail;
  return [...parts, detail];
}

// Letters typed within this pause extend the search; a longer pause starts a new one.
const TYPEAHEAD_MS = 700;

// A plain printable key, not a shortcut.
const isLetter = (event) =>
  event.key.length === 1 && !event.ctrlKey && !event.metaKey && !event.altKey;

class SelectMenu {
  active = -1;
  typed = "";
  typedAt = -Infinity;
  // Whether the menu was open when the trigger was pressed: light dismiss closes it before
  // the click, which must then not reopen it, however long the press lasts. `justClosed`
  // covers a dismissal that runs before the trigger hears the press.
  openAtPress = false;
  justClosed = false;

  constructor(select) {
    this.select = select;
    this.wrapper = element("div", "select");
    this.trigger = element("button", "select-trigger");
    this.text = element("span", "select-value");
    this.mark = element("span", "select-swatch");
    this.list = element("div", "select-menu");
    this.#build();
    this.#label();
    this.#listen();
    this.#mirrorValue();
    this.refresh();
  }

  get isOpen() {
    return this.list.matches(":popover-open");
  }

  get isMenu() {
    return "menu" in this.select.dataset;
  }

  get items() {
    return [...this.list.querySelectorAll('[role="option"]')];
  }

  #build() {
    const { select, trigger, list } = this;
    trigger.type = "button";
    trigger.id = `${select.id}-trigger`;
    trigger.setAttribute("role", "combobox");
    trigger.setAttribute("aria-haspopup", "listbox");
    trigger.setAttribute("aria-expanded", "false");
    list.id = `${select.id}-menu`;
    list.setAttribute("role", "listbox");
    list.popover = "auto";
    list.tabIndex = -1;
    trigger.setAttribute("aria-controls", list.id);
    if (this.isMenu) {
      trigger.classList.add("btn-quiet", "btn-sm");
      trigger.append(icon("add"), this.text);
    } else trigger.append(this.mark, this.text, icon("chevron-down"));
    select.before(this.wrapper);
    this.wrapper.append(select, trigger, list);
    select.classList.add("select-native");
    select.tabIndex = -1;
    select.setAttribute("aria-hidden", "true");
  }

  #label() {
    const label = document.querySelector(`label[for="${this.select.id}"]`);
    if (!label) return;
    label.id ||= `${this.select.id}-label`;
    this.trigger.setAttribute("aria-labelledby", `${label.id} ${this.trigger.id}`);
    this.list.setAttribute("aria-labelledby", label.id);
    label.addEventListener("click", (event) => {
      event.preventDefault();
      if (!this.trigger.disabled) this.trigger.focus();
    });
  }

  #listen() {
    this.list.addEventListener("toggle", (event) => this.#toggled(event.newState === "open"));
    this.list.addEventListener("beforetoggle", (event) => {
      if (event.newState !== "closed") return;
      this.justClosed = true;
      setTimeout(() => {
        this.justClosed = false;
      });
    });
    this.trigger.addEventListener("pointerdown", () => {
      this.openAtPress = this.isOpen || this.justClosed;
    });
    this.trigger.addEventListener("click", () => this.#clicked());
    this.trigger.addEventListener("keydown", (event) => this.#keydown(event));
    this.select.addEventListener("change", this.refresh);
    new MutationObserver(this.#changed).observe(this.select, {
      attributes: true,
      attributeFilter: ["disabled"],
      childList: true,
      subtree: true,
    });
  }

  // Programmatic value changes keep the trigger in sync without extra calls.
  #mirrorValue() {
    const { select, refresh } = this;
    Object.defineProperty(select, "value", {
      configurable: true,
      get: () => valueDescriptor.get.call(select),
      set: (value) => {
        valueDescriptor.set.call(select, value);
        refresh();
      },
    });
  }

  // Options that change while the menu is open, such as a list that finished loading,
  // show at once, keeping the highlighted option.
  #changed = () => {
    this.refresh();
    if (!this.isOpen) return;
    const value = this.items[this.active]?.dataset.value ?? this.select.value;
    this.#render();
    this.place();
    this.highlight(this.items.findIndex((item) => item.dataset.value === value));
  };

  refresh = () => {
    const option = this.select.selectedOptions[0];
    this.wrapper.classList.toggle("is-menu", this.isMenu);
    this.#refreshText(option);
    this.#refreshSwatch(option?.dataset);
    this.#refreshPlaceholder(option);
    this.trigger.disabled = this.select.disabled;
    this.wrapper.classList.toggle("is-disabled", this.select.disabled);
  };

  #refreshText(option) {
    const text = this.isMenu ? "" : selectedText(option);
    this.text.textContent = text || this.select.dataset.placeholder || "";
  }

  #refreshSwatch({ swatch } = {}) {
    // The chosen option's swatch, if it has one, leads the trigger.
    this.mark.hidden = !swatch;
    this.mark.style.background = swatch || "";
  }

  #refreshPlaceholder(option) {
    this.trigger.classList.toggle(
      "is-placeholder",
      !this.isMenu && !option?.value && !!this.select.dataset.placeholder,
    );
  }

  #render() {
    this.list.replaceChildren();
    for (const node of this.select.children) {
      if (node.tagName === "OPTGROUP") this.#renderGroup(node);
      else this.#renderOption(node);
    }
  }

  #renderGroup(group) {
    const heading = element("div", "select-group");
    heading.textContent = group.label;
    heading.setAttribute("role", "presentation");
    this.list.append(heading);
    for (const option of group.children) this.#renderOption(option);
  }

  #renderOption(option) {
    if (option.hidden) return;
    const item = element("div", "select-option");
    item.setAttribute("role", "option");
    item.id = `${this.list.id}-${this.list.childElementCount}`;
    item.dataset.value = option.value;
    item.setAttribute("aria-selected", String(option.selected));
    if (option.disabled) item.setAttribute("aria-disabled", "true");
    this.#decorate(item, option.dataset);
    item.append(...optionText(option), icon("check"));
    item.addEventListener("pointerup", () => this.choose(option.value));
    item.addEventListener("pointermove", () => this.highlight(this.items.indexOf(item)));
    this.list.append(item);
  }

  // A swatch leads an option with `data-swatch`; a `data-font` option shows its name in that
  // font where the browser has it.
  #decorate(item, { swatch, font }) {
    if (swatch) item.append(this.#swatch(swatch));
    if (font) item.style.fontFamily = `"${font}", inherit`;
  }

  #swatch(background) {
    const swatch = element("span", "select-swatch");
    swatch.style.background = background;
    return swatch;
  }

  highlight(index) {
    const items = this.items;
    this.active = Math.max(0, Math.min(items.length - 1, index));
    for (const [position, item] of items.entries()) {
      item.classList.toggle("is-active", position === this.active);
    }
    const item = items[this.active];
    if (!item) return;
    this.trigger.setAttribute("aria-activedescendant", item.id);
    revealOption(this.list, item);
  }

  place() {
    placeMenu(this.trigger, this.list);
  }

  open() {
    if (this.trigger.disabled) return;
    this.#render();
    this.list.showPopover();
    this.place();
    this.highlight(this.items.findIndex((item) => item.dataset.value === this.select.value));
  }

  close(focus = true) {
    if (this.isOpen) this.list.hidePopover();
    if (focus) this.trigger.focus();
  }

  choose(value) {
    const option = [...this.select.options].find((item) => item.value === value);
    if (!available(option)) return;
    this.close();
    if (this.select.value === value) return;
    valueDescriptor.set.call(this.select, value);
    this.refresh();
    this.select.dispatchEvent(new Event("change", { bubbles: true }));
    if (this.isMenu) valueDescriptor.set.call(this.select, "");
  }

  #toggled(opened) {
    this.trigger.setAttribute("aria-expanded", String(opened));
    this.wrapper.classList.toggle("is-open", opened);
    if (opened) {
      openMenu = this;
      return;
    }
    if (openMenu === this) openMenu = null;
    this.trigger.removeAttribute("aria-activedescendant");
  }

  #clicked() {
    if (this.isOpen) this.close();
    else if (!this.openAtPress) this.open();
    this.openAtPress = false;
  }

  #keydown(event) {
    const keys = {
      ArrowDown: () => this.#step(event, 1),
      ArrowUp: () => this.#step(event, -1),
      Enter: () => this.#pick(event),
      " ": () => this.#pick(event),
      Escape: () => this.#dismiss(event),
      Tab: () => this.isOpen && this.close(false),
      Home: () => this.#edge(event, 0),
      End: () => this.#edge(event, this.items.length - 1),
    };
    (keys[event.key] || (() => this.#typeahead(event)))();
  }

  // Typing jumps to the first option that starts with the letters, like a native select.
  #typeahead(event) {
    if (!isLetter(event)) return;
    event.preventDefault();
    if (!this.isOpen) this.open();
    const typed = this.#type(event.key.toLowerCase(), event.timeStamp);
    const index = this.items.findIndex((item) => item.textContent.toLowerCase().startsWith(typed));
    if (index >= 0) this.highlight(index);
  }

  // The letters typed so far, restarting after a pause.
  #type(letter, time) {
    this.typed = time - this.typedAt < TYPEAHEAD_MS ? this.typed + letter : letter;
    this.typedAt = time;
    return this.typed;
  }

  // Arrows open a closed menu, then move past disabled options.
  #step(event, step) {
    event.preventDefault();
    if (!this.isOpen) {
      this.open();
      return;
    }
    const items = this.items;
    let next = this.active + step;
    while (items[next]?.getAttribute("aria-disabled") === "true") next += step;
    if (items[next]) this.highlight(next);
  }

  #pick(event) {
    if (!this.isOpen) return;
    event.preventDefault();
    const item = this.items[this.active];
    if (item) this.choose(item.dataset.value);
  }

  #dismiss(event) {
    if (!this.isOpen) return;
    event.preventDefault();
    event.stopPropagation();
    this.close();
  }

  #edge(event, index) {
    if (!this.isOpen) return;
    event.preventDefault();
    this.highlight(index);
  }
}

export function enhanceSelect(select) {
  select.menu ??= new SelectMenu(select);
  return select.menu;
}
