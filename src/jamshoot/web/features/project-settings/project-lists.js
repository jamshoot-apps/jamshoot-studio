// Project membership lists; preview context stays in the canvas toolbar.
import { $ } from "../../shared/lib/dom.js";
import { button } from "../../shared/ui/button/button.js";
import { enhanceSelect } from "../../shared/ui/select/select.js";
import { suggest } from "../../shared/ui/select/suggest.js";

const languageNames = new Intl.DisplayNames([document.documentElement.lang || "en"], {
  type: "language",
});

function languageName(locale) {
  try {
    return languageNames.of(locale);
  } catch {
    return locale;
  }
}

// App Store Connect's localizations, all listed and narrowed while typing; any other name
// works too.
const STORE_LOCALES = [
  "ar-SA",
  "ca",
  "cs",
  "da",
  "de-DE",
  "el",
  "en-AU",
  "en-CA",
  "en-GB",
  "en-US",
  "es-ES",
  "es-MX",
  "fi",
  "fr-CA",
  "fr-FR",
  "he",
  "hi",
  "hr",
  "hu",
  "id",
  "it",
  "ja",
  "ko",
  "ms",
  "nl-NL",
  "no",
  "pl",
  "pt-BR",
  "pt-PT",
  "ro",
  "ru",
  "sk",
  "sv",
  "th",
  "tr",
  "uk",
  "vi",
  "zh-Hans",
  "zh-Hant",
];

const COLLECTIONS = {
  locale: {
    noun: "language",
    list: "locales",
    name: languageName,
    add: (state, value, source) => state.addLocale(value, source),
    remove: (state, id) => state.removeLocale(id),
  },
  variant: {
    noun: "variant",
    list: "variants",
    name: (id) => id,
    add: (state, value) => state.addVariant(value),
    remove: (state, id) => state.removeVariant(id),
  },
};

function element(tag, className, text = "") {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

class ProjectList {
  editing = null;
  signature = "";

  constructor(kind, context) {
    Object.assign(this, context, COLLECTIONS[kind], { kind });
    this.root = $(`project-${this.list}`);
    this.editor = $(`${kind}-editor`);
    this.addButton = $(`new-${kind}`);
    this.notice = $(`${kind}-notice`);
    this.addButton.addEventListener("click", () => this.open());
  }

  ids() {
    const state = this.getState();
    return this.kind === "locale" ? state.project.locales : state.variants.map((item) => item.id);
  }

  clearNotice() {
    this.notice.hidden = true;
    this.notice.replaceChildren();
  }

  update(force = false) {
    const state = this.getState(),
      ids = this.ids();
    const signature = JSON.stringify([ids, !!state.project.variants]);
    this.addButton.disabled = ids.length >= state.limitOf(this.list);
    $(`${this.kind}-count`).textContent = ids.length;
    if (!force && signature === this.signature) return;
    this.signature = signature;
    this.clearNotice();
    this.close(false);
    this.root.replaceChildren(...ids.map((id) => this.row(id)));
  }

  row(id) {
    const state = this.getState(),
      row = element("li", "project-list-row");
    row.dataset.id = id;
    row.append(this.rowText(state, id));
    if (this.kind === "variant")
      row.append(
        button({
          label: `Rename variant ${id}`,
          icon: "edit",
          variant: "quiet",
          iconOnly: true,
          onClick: () => this.open(id),
        }),
      );
    const removable =
      this.kind === "locale" ? state.project.locales.length > 1 : !!state.project.variants;
    if (removable)
      row.append(
        button({
          label: `Remove ${this.noun} ${id}`,
          icon: "close",
          variant: "quiet",
          iconOnly: true,
          onClick: () => this.removeItem(id),
        }),
      );
    return row;
  }

  rowDetail(state, id) {
    if (this.kind === "locale") return this.name(id) !== id ? id : "";
    return state.project.variants ? "" : "Default output";
  }

  rowText(state, id) {
    const text = element("div", "project-list-name", this.name(id));
    const detail = this.rowDetail(state, id);
    if (detail) text.append(element("small", "detail", detail));
    return text;
  }

  removeItem(id) {
    try {
      this.change((state) => this.remove(state, id), `Remove ${this.noun}`);
      this.update(true);
      this.notice.append(
        document.createTextNode(`${this.name(id)} removed. `),
        button({
          label: "Undo",
          variant: "quiet",
          size: "sm",
          onClick: () => {
            this.undo();
            this.clearNotice();
            this.addButton.focus();
          },
        }),
      );
      this.notice.hidden = false;
      this.notice.querySelector("button").focus();
    } catch (error) {
      this.notice.textContent = error.message;
      this.notice.hidden = false;
    }
  }

  close(focus = true) {
    const previous = this.editing;
    this.editing = null;
    this.editor.hidden = true;
    this.editor.replaceChildren();
    this.addButton.setAttribute("aria-expanded", "false");
    if (!focus) return;
    this.update(true);
    const target = this.root.querySelector(`[data-id="${previous}"] button`);
    (target || this.addButton).focus();
  }

  open(id = null) {
    this.update(true);
    this.editing = id;
    this.clearNotice();
    const form = this.form(id);
    if (id) this.root.querySelector(`[data-id="${id}"]`).replaceChildren(form);
    else {
      this.editor.append(form);
      this.editor.hidden = false;
      this.addButton.setAttribute("aria-expanded", "true");
    }
    const [input, source] = [form.querySelector("input"), form.querySelector("select")];
    if (source) enhanceSelect(source);
    if (this.kind === "locale") {
      const used = new Set(this.ids());
      suggest(
        input,
        STORE_LOCALES.filter((code) => !used.has(code))
          .map((code) => ({ value: code, label: languageName(code) }))
          .sort((a, b) => a.label.localeCompare(b.label)),
      );
    }
    input.focus();
    input.select();
  }

  sourceField(form) {
    const label = element("label", "", "Copy text and screenshots from");
    const select = document.createElement("select");
    select.id = "locale-source";
    label.htmlFor = select.id;
    select.append(...this.ids().map((id) => new Option(`${this.name(id)} · ${id}`, id)));
    select.value = this.getState().selection.locale;
    form.append(label, select);
    return select;
  }

  form(id) {
    const form = element("form", "project-inline-editor"),
      label = element("label", "", this.fieldCaption(id)),
      input = document.createElement("input"),
      error = element("p", "project-field-error");
    input.id = `${this.kind}-input`;
    input.type = "text";
    input.maxLength = 64;
    input.autocomplete = "off";
    input.spellcheck = false;
    input.value = id || "";
    input.placeholder = this.kind === "locale" ? "Name or code, e.g. pt-BR" : "e.g. dark";
    label.htmlFor = input.id;
    error.id = `${input.id}-error`;
    error.setAttribute("role", "alert");
    input.setAttribute("aria-describedby", error.id);
    const actions = element("div", "project-list-actions");
    const save = button({ label: id ? "Save" : `Add ${this.noun}`, variant: "primary" });
    save.type = "submit";
    actions.append(
      save,
      button({ label: "Cancel", variant: "quiet", onClick: () => this.close() }),
    );
    form.append(label, input);
    const source = this.copySource(form);
    form.append(error, actions);
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      this.submit({ id, input, source, error });
    });
    input.addEventListener("input", () => {
      input.removeAttribute("aria-invalid");
      error.textContent = "";
    });
    form.addEventListener("keydown", (event) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      this.close();
    });
    return form;
  }

  fieldCaption(id) {
    if (id) return "Variant id";
    return `New ${this.noun === "language" ? "language" : "variant id"}`;
  }

  copySource(form) {
    return this.kind === "locale" ? this.sourceField(form) : null;
  }

  submit({ id, input, source, error }) {
    try {
      this.change(
        (state) => {
          if (id) state.renameVariant(id, input.value);
          else {
            const selected = state.selection[this.kind];
            this.add(state, input.value, source?.value);
            state.select(this.kind, selected);
          }
        },
        id ? "Rename variant" : `Add ${this.noun}`,
      );
      this.close();
    } catch (failure) {
      input.setAttribute("aria-invalid", "true");
      error.textContent = failure.message;
      input.focus();
    }
  }
}

export function projectLists(context) {
  const lists = Object.keys(COLLECTIONS).map((kind) => new ProjectList(kind, context));
  return {
    update() {
      for (const list of lists) list.update();
    },
    clearNotice() {
      for (const list of lists) list.clearNotice();
    },
  };
}
