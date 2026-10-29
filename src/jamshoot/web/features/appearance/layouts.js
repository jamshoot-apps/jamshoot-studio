// Spacing: a template chooser with adjustments per scope, and the template library in
// Project → Layout.

import { $ } from "../../shared/lib/dom.js";
import { layoutDefaults } from "../../shared/model/project.js";
import { rangeSession } from "../../shared/ui/range-control/range-control.js";
import { enhanceSelect } from "../../shared/ui/select/select.js";
import { StyleLibrary } from "./style-library.js";
import { measuredRange, spacingExtent, unitSwitch } from "./units.js";

const LAYOUT_CAPTIONS = {
  topMargin: "Top margin",
  labelGap: "Eyebrow to headline",
  subtitleGap: "Headline to text",
  textWidth: "Text width",
  screenshotGap: "Text to screenshot",
  screenshotTop: "Screenshot top (0 = after text)",
  screenshotWidth: "Screenshot width",
  bottomMargin: "Bottom margin",
};

// Text sizes, weights and line height are set under Typography.
// `extent(key)` is how many pixels 100 % of `key` spans on the previewed size.
function layoutRanges(container, idPrefix, schema, onChange, session, extent) {
  const ranges = {};
  for (const [key, limits] of Object.entries(schema.$defs.layoutSettings.properties))
    ranges[key] = measuredRange(
      container,
      `${idPrefix}${key}`,
      LAYOUT_CAPTIONS[key],
      limits,
      (value) => onChange(key, value),
      session,
      () => extent(key),
    );
  return ranges;
}

function templateOptions(prefix, templates) {
  const items = [];
  if (!prefix) items.push(new Option("Project default", ""));
  items.push(new Option("Built-in", "builtin"));
  if (templates.length) {
    const group = document.createElement("optgroup");
    group.label = "Layout templates";
    group.append(...templates.map((item) => new Option(item.name, `style:${item.id}`)));
    items.push(group);
  }
  return items;
}

function templateSource(prefix, value, linked) {
  if (linked) return `Linked to “${linked.name}”`;
  return prefix || value ? "Built-in spacing" : "Uses the project layout";
}

// `previewTarget()` is the previewed output size, so values show as the preview renders them.
class LayoutControls {
  notice = "";

  constructor(prefix, { schema, getState, previewTarget, changed, editSession }) {
    Object.assign(this, { prefix, getState, previewTarget, changed });
    this.scope = prefix ? "project" : "slide";
    this.select = $(`${prefix}layout-template`);
    enhanceSelect(this.select);
    this.select.addEventListener("change", () => {
      this.notice = "";
      getState().setLayoutStyle(this.scope, this.select.value);
      changed("Choose layout template");
    });
    $(`${prefix}save-layout-template`).addEventListener("click", () => this.#save());
    $(`${prefix}reset-layout-settings`).addEventListener("click", () => {
      getState().resetStyleGroup("layoutSettings", this.scope);
      changed("Reset spacing");
    });
    this.ranges = layoutRanges(
      $(`${prefix}layout-settings`),
      `${prefix}layout-`,
      schema,
      (key, value) => {
        getState().setStyleOption("layoutSettings", key, value, this.scope);
        changed("Adjust layout");
      },
      rangeSession(editSession, "Adjust layout"),
      (key) => {
        const target = previewTarget();
        return spacingExtent(key, target);
      },
    );
  }

  // Every spacing value the scope renders with, so a saved template keeps the look on any
  // slide.
  get values() {
    const style = this.getState().styleOf(this.scope);
    return { ...layoutDefaults(style, this.previewTarget()), ...style.layoutSettings };
  }

  #save() {
    const state = this.getState(),
      name = state.nextStyleName("layout");
    state.saveSavedStyle("layout", name, { layoutSettings: this.values }, this.scope);
    this.notice = `Saved as “${name}”. Rename or edit it in Project → Layout.`;
    this.changed("Save layout template");
  }

  // Rebuilt only when templates or the choice change, so an open menu stays put.
  #renderOptions(templates, value) {
    const signature = JSON.stringify([templates.map((item) => [item.id, item.name]), value]);
    if (this.select.dataset.signature === signature) return;
    this.select.dataset.signature = signature;
    this.select.replaceChildren(...templateOptions(this.prefix, templates));
  }

  update(disabled) {
    const { prefix, scope } = this,
      state = this.getState(),
      templates = state.project.layoutStyles || [],
      value = state.layoutValue(scope);
    this.#renderOptions(templates, value);
    this.select.value = value;
    this.select.disabled = disabled;
    $(`${prefix}save-layout-template`).disabled = disabled || state.isFull("layoutStyles");
    const own = this.#updateSpacing(state, disabled);
    this.#updateStatus(templates, value, own);
  }

  #updateSpacing(state, disabled) {
    const { prefix, scope } = this;
    const values = this.values;
    unitSwitch($(`${prefix}units`));
    for (const [key, control] of Object.entries(this.ranges)) control.update(values[key]);
    const own = Object.keys(state.ownStyle(scope).layoutSettings || {}).length;
    $(`${prefix}layout-settings`).disabled = disabled;
    $(`${prefix}reset-layout-settings`).disabled = disabled || !own;
    return own;
  }

  #updateStatus(templates, value, own) {
    const { prefix } = this;
    const source = templateSource(
      prefix,
      value,
      templates.find((item) => `style:${item.id}` === value),
    );
    const changes = `${own} ${own === 1 ? "setting" : "settings"} changed here`;
    $(`${prefix}layout-template-status`).textContent =
      this.notice || (own ? `${source} · ${changes}` : source);
  }
}

export function layoutControls(prefix, context) {
  return new LayoutControls(prefix, context);
}

function templateMark() {
  const mark = document.createElement("span");
  mark.className = "icon icon-options template-mark";
  mark.setAttribute("aria-hidden", "true");
  return mark;
}

class LayoutLibrary {
  constructor({ schema, getState, previewTarget, changed, editSession }) {
    const builtIn = () => layoutDefaults(getState().defaultStyle, previewTarget());
    this.library = new StyleLibrary(
      {
        kind: "layout",
        idPrefix: "template",
        elements: {
          list: $("layout-template-list"),
          add: $("new-layout-template"),
          count: $("layout-template-count"),
        },
        text: {
          empty: "No layout templates yet. Save a slide's spacing to reuse it on other slides.",
          kept: "spacing",
        },
      },
      {
        getState,
        changed,
        preview: templateMark,
        newValues: () => ({
          layoutSettings: { ...builtIn(), ...getState().defaultStyle.layoutSettings },
        }),
        showValues: (current) => {
          const values = { ...builtIn(), ...current.layoutSettings };
          for (const [key, control] of Object.entries(this.ranges)) control.update(values[key]);
        },
      },
    );
    this.ranges = layoutRanges(
      this.library.fields,
      "template-",
      schema,
      (key, value) => this.library.setValue(key, value),
      rangeSession(editSession, "Edit layout template"),
      (key) => {
        const target = previewTarget();
        return spacingExtent(key, target);
      },
    );
  }

  update() {
    this.library.update();
  }

  reset() {
    this.library.reset();
  }
}

export function layoutLibrary(context) {
  return new LayoutLibrary(context);
}
