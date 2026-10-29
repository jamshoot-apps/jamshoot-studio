// Slides and Settings panels: docked from 64rem, below that one modal drawer at a time.
import { $ } from "../../shared/lib/dom.js";
import { containTab } from "../../shared/ui/dialogs/dialogs.js";

const PANELS = ["slides-panel", "inspector-panel"];

class Panels {
  narrow = matchMedia("not all and (min-width: 64rem)");
  opened = null;
  docked = { "slides-panel": true, "inspector-panel": true };

  constructor() {
    for (const id of PANELS) {
      $(`toggle-${id}`).addEventListener("click", () => this.#toggle(id));
      $(id)
        .querySelector("[data-close-panel]")
        .addEventListener("click", () => this.#hide(id));
    }
    $("panel-backdrop").addEventListener("click", this.close);
    document.addEventListener("keydown", (event) => this.#keydown(event));
    this.narrow.addEventListener("change", () => this.#resized());
    this.sync();
  }

  isNarrow = () => this.narrow.matches;

  get #drawer() {
    return this.narrow.matches ? this.opened : null;
  }

  sync() {
    for (const id of PANELS) {
      this.#show(id, this.narrow.matches ? this.opened === id : this.docked[id]);
    }
    const modal = this.#drawer !== null;
    $("panel-backdrop").hidden = !modal;
    $("workspace").inert = modal;
    $("topbar").inert = modal;
  }

  // An open drawer is a modal dialog; a docked panel is a plain region.
  #show(id, visible) {
    const panel = $(id);
    panel.hidden = !visible;
    $(`toggle-${id}`).setAttribute("aria-expanded", String(visible));
    $("editor").classList.toggle(`without-${id}`, !visible);
    panel.removeAttribute("role");
    panel.removeAttribute("aria-modal");
    if (!visible || !this.narrow.matches) return;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-modal", "true");
  }

  close = () => {
    const previous = this.opened;
    this.opened = null;
    this.sync();
    if (previous) $(`toggle-${previous}`).focus();
  };

  #toggle(id) {
    if (this.narrow.matches) this.opened = this.opened === id ? null : id;
    else this.docked[id] = !this.docked[id];
    this.sync();
    if (this.opened) $(this.opened).querySelector("button").focus();
  }

  #hide(id) {
    if (this.narrow.matches) {
      this.close();
      return;
    }
    this.docked[id] = false;
    this.sync();
    $(`toggle-${id}`).focus();
  }

  // A drawer behaves like a dialog: Escape closes it and Tab stays inside.
  #keydown(event) {
    const drawer = this.#drawer;
    if (!drawer || document.querySelector("dialog:modal")) return;
    if (event.key === "Escape") {
      event.preventDefault();
      this.close();
      return;
    }
    containTab(event, $(drawer));
  }

  // Crossing 64rem closes drawers; focus leaves a panel that is now hidden.
  #resized() {
    const focused = document.activeElement?.closest(".panel")?.id;
    this.opened = null;
    this.sync();
    if (focused && $(focused).hidden) $(`toggle-${focused}`).focus();
  }
}

export function panelController() {
  return new Panels();
}
