// Typography per text field: a field switch, font, case and sizes for the project defaults
// (prefix "default-") and as slide overrides (prefix ""), and the project's fonts.

import { $ } from "../../shared/lib/dom.js";
import { textSettings } from "../../shared/model/project.js";
import { choices } from "../../shared/ui/choice-group/choice-group.js";
import { rangeControl, rangeSession } from "../../shared/ui/range-control/range-control.js";
import { enhanceSelect } from "../../shared/ui/select/select.js";
import { measuredRange, unitSwitch } from "./units.js";

const FIELD_LABELS = {
  featureLabel: "Eyebrow",
  headline: "Headline",
  subtitle: "Supporting text",
};
const SHORT_LABELS = { featureLabel: "Eyebrow", headline: "Headline", subtitle: "Text" };
const CAPTIONS = {
  weight: "Weight",
  lineHeight: "Line height (%)",
  letterSpacing: "Letter spacing (%)",
};
const CASES = { typed: "As typed", upper: "Capitals" };

// The project's fonts and the installed ones, fetched once on first use; `onChange` runs
// when either list changes.
export class FontLibrary {
  families = { project: [], system: [] };
  loaded = false;
  #request = null;

  constructor(api, onChange = () => {}) {
    Object.assign(this, { api, onChange });
  }

  load() {
    this.#request ??= this.api("/fonts").then(
      (families) => {
        this.families = families;
        this.loaded = true;
        this.onChange();
      },
      (error) => {
        this.#request = null;
        throw error;
      },
    );
    return this.#request;
  }

  // Stores `file` in the project's fonts; returns the families it added.
  async upload(file) {
    const name = encodeURIComponent(file.name);
    const result = await this.api(`/fonts?name=${name}`, file, { raw: true });
    this.families = { ...this.families, project: result.project };
    this.onChange();
    return result.families;
  }
}

function fontOption(family, detail) {
  const option = new Option(family, family);
  option.dataset.font = family;
  if (detail) option.dataset.detail = detail;
  return option;
}

function familyGroup(label, families) {
  const group = document.createElement("optgroup");
  group.label = label;
  group.append(
    ...families.map((item) =>
      fontOption(item.family, item.variable ? "Variable" : `${item.styles.length} styles`),
    ),
  );
  return group;
}

// Built-in first (unless the slide inherits a font, which it then could not return to),
// then the project's fonts and the installed ones. A chosen family missing from both lists
// stays listed, marked as such once the lists are known.
function fontOptions(fonts, current, offerBuiltIn) {
  const { project, system } = fonts.families;
  const known = new Set([...project, ...system].map((item) => item.family));
  const items = [];
  if (offerBuiltIn) items.push(new Option("Built-in font", ""));
  items.push(...missingFont(fonts, current, known));
  const groups = [
    ["In this project", project],
    ["Installed on this computer", system],
  ];
  items.push(
    ...groups
      .filter(([, families]) => families.length)
      .map(([label, families]) => familyGroup(label, families)),
  );
  if (!fonts.loaded) {
    const loading = new Option("Loading installed fonts…", "loading");
    loading.disabled = true;
    items.push(loading);
  }
  return items;
}

function missingFont(fonts, current, known) {
  if (current && !known.has(current)) return [fontOption(current, fonts.loaded ? "Not found" : "")];
  return [];
}

class TypographyControls {
  field = "headline";

  constructor(prefix, { schema, getState, previewTarget, changed, editSession, fonts }) {
    Object.assign(this, { prefix, getState, previewTarget, changed, fonts });
    this.scope = prefix ? "project" : "slide";
    this.root = $(`${prefix}typography`);
    this.font = $(`${prefix}type-font`);
    enhanceSelect(this.font);
    this.font.addEventListener("change", () => this.#chooseFont());
    // The installed fonts are listed on first use, not on every page load.
    this.font.menu.trigger.addEventListener("pointerdown", () => this.#loadFonts());
    this.font.menu.trigger.addEventListener("focus", () => this.#loadFonts());
    const limits = schema.$defs.text_style.properties;
    const session = rangeSession(editSession, "Adjust typography");
    // Size is a % of the canvas height, so it can show as pixels too.
    this.ranges = {
      size: measuredRange(
        $(`${prefix}type-ranges`),
        `${prefix}type-size`,
        "Size",
        limits.size,
        (value) => this.#set("size", value, "Adjust typography"),
        session,
        () => previewTarget().height,
      ),
    };
    for (const [key, caption] of Object.entries(CAPTIONS))
      this.ranges[key] = rangeControl(
        $(`${prefix}type-ranges`),
        `${prefix}type-${key}`,
        caption,
        limits[key],
        (value) => this.#set(key, value, "Adjust typography"),
        session,
      );
    $(`${prefix}reset-typography`).addEventListener("click", () => {
      getState().resetTypography(this.scope, this.field);
      changed(`Reset ${FIELD_LABELS[this.field].toLowerCase()} typography`);
    });
  }

  #loadFonts() {
    this.fonts.load().catch(() => {});
  }

  #set(key, value, label) {
    this.getState().setTextStyle(this.field, key, value, this.scope);
    this.changed(label);
  }

  // The family the scope inherits for the field: the project's for a slide, none for it.
  #inheritedFont() {
    if (this.scope === "project") return null;
    const style = this.getState().inheritedStyle();
    return textSettings(style, this.previewTarget())[this.field].font;
  }

  // Choosing what the slide inherits drops its override instead of repeating it.
  #chooseFont() {
    const value = this.font.value || null;
    const stored = value === this.#inheritedFont() ? undefined : (value ?? undefined);
    this.#set("font", stored, "Change font");
  }

  #renderFont(current, disabled) {
    const offerBuiltIn = !this.#inheritedFont();
    const items = fontOptions(this.fonts, current, offerBuiltIn);
    const signature = JSON.stringify([
      items.map((item) => item.outerHTML),
      this.fonts.families.project.length,
    ]);
    if (this.font.dataset.signature !== signature) {
      this.font.dataset.signature = signature;
      this.font.replaceChildren(...items);
    }
    this.font.value = current || "";
    this.font.disabled = disabled;
  }

  update(disabled) {
    const state = this.getState(),
      own = state.ownStyle(this.scope).typography || {};
    const settings = textSettings(state.styleOf(this.scope), this.previewTarget());
    choices(
      $(`${this.prefix}type-field`),
      Object.keys(FIELD_LABELS),
      this.field,
      (field) => {
        this.field = field;
        this.update(disabled);
      },
      (field) => (own[field] ? `${SHORT_LABELS[field]} •` : SHORT_LABELS[field]),
    );
    const current = settings[this.field];
    this.#renderFont(current.font, disabled);
    unitSwitch($(`${this.prefix}type-units`));
    for (const [key, control] of Object.entries(this.ranges)) control.update(current[key]);
    choices(
      $(`${this.prefix}type-case`),
      Object.keys(CASES),
      current.uppercase ? "upper" : "typed",
      (value) => this.#set("uppercase", value === "upper", "Change text case"),
      (value) => CASES[value],
    );
    this.root.disabled = disabled;
    this.#updateReset(own, disabled);
  }

  #updateReset(own, disabled) {
    const reset = $(`${this.prefix}reset-typography`);
    reset.disabled = disabled || !own[this.field];
    reset.lastChild.textContent = `Reset ${FIELD_LABELS[this.field].toLowerCase()}`;
    const changes = Object.values(own).reduce((sum, values) => sum + Object.keys(values).length, 0);
    const badge = $(`${this.prefix}typography-count`);
    if (badge) {
      badge.hidden = !changes;
      badge.textContent = String(changes);
    }
  }
}

export function typographyControls(prefix, context) {
  return new TypographyControls(prefix, context);
}

// The project's own font families, each with its styles.
export function renderProjectFonts(list, families) {
  list.replaceChildren(
    ...families.map((item) => {
      const row = document.createElement("li"),
        name = document.createElement("div"),
        sample = document.createElement("span"),
        detail = document.createElement("small");
      row.className = "project-list-row";
      name.className = "project-list-name";
      sample.textContent = item.family;
      sample.style.fontFamily = `"${item.family}", inherit`;
      detail.className = "detail";
      detail.textContent = item.variable ? "Variable" : item.styles.join(", ");
      name.append(sample, detail);
      row.append(name);
      return row;
    }),
  );
}
