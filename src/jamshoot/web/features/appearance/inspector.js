// The settings panel for the active slide (prefix "") and the project defaults ("default-").

import { $ } from "../../shared/lib/dom.js";
import { title, words } from "../../shared/lib/text.js";
import { platformName } from "../../shared/model/platforms.js";
import { layoutChoices, resolvedLayout } from "../../shared/model/project.js";
import { choices } from "../../shared/ui/choice-group/choice-group.js";
import { appearanceControls } from "./background.js";
import { layoutControls, layoutLibrary } from "./layouts.js";
import { paletteManager } from "./palette-manager.js";
import { paletteControl } from "./palettes.js";
import { typographyControls } from "./typography.js";

const LABELS = {
  auto: "Automatic",
  "window-top": "App window",
  "device-top": "Device",
  "device-focus": "Large device",
  raw: "Image only",
  contain: "Match screenshot",
  cover: "Crop to display",
  text: "Text",
  badge: "Badge",
};
// Element id and copy key of each slide text field.
export const TEXT_INPUTS = [
  ["headline", "headline"],
  ["subtitle", "subtitle"],
  ["feature-label", "featureLabel"],
];
const PREFIXES = ["", "default-"];
const STYLE_CHOICES = ["pattern", "layout", "deviceFrame", "screenshotFit", "labelStyle"];
const COLOR_EDIT_LABELS = { "": "Edit slide color", "default-": "Edit default color" };
// History names for edits and resets of each appearance group.
const EDIT_NAMES = {
  colors: "Edit color",
  gradient: "Adjust gradient",
  patternSettings: "Adjust pattern",
};
const GROUP_NAMES = {
  palette: "palette changes",
  background: "background",
  gradient: "gradient",
  patternSettings: "pattern adjustments",
};
export const optionLabel = (value) => LABELS[value] || title(value);
const scopeOf = (prefix) => (prefix ? "project" : "slide");

export class Inspector {
  styleEditors = {};
  palettes = {};
  layouts = {};
  typography = {};

  // `editor` holds the draft (`state`) and the project's images (`assets`); `fonts` lists
  // the font families Typography offers.
  constructor(editor, { targetOf, changed, editSession, fonts }) {
    Object.assign(this, { editor, targetOf, changed, editSession, fonts });
    for (const prefix of PREFIXES) this.#listenSeed(prefix);
    $("reset-style").addEventListener("click", () => {
      editor.state.resetStyle();
      this.restyled("Reset slide appearance");
    });
    $("existing-asset").addEventListener("change", () => this.#chooseAsset());
  }

  get #previewTarget() {
    return this.targetOf(this.editor.state.selection.target);
  }

  // The first load builds the controls; a reload only closes the library entry being edited.
  load({ schema, appearance }) {
    if (this.paletteManager) {
      this.paletteManager.update();
      this.layoutLibrary.reset();
      return;
    }
    this.schema = schema;
    const restyled = (label) => this.restyled(label);
    const getState = () => this.editor.state;
    const previewTarget = () => this.#previewTarget;
    this.paletteManager = paletteManager({
      schema,
      appearance,
      getState,
      changed: restyled,
      editSession: this.editSession,
    });
    const openManager = (value) => this.#openPalette(value);
    const context = {
      schema,
      getState,
      previewTarget,
      changed: restyled,
      editSession: this.editSession,
      fonts: this.fonts,
    };
    this.layoutLibrary = layoutLibrary(context);
    for (const prefix of PREFIXES) {
      this.palettes[prefix] = paletteControl(prefix, {
        getState,
        appearance,
        changed: restyled,
        openManager,
      });
      this.styleEditors[prefix] = this.#createStyleEditor(prefix, appearance);
      this.layouts[prefix] = layoutControls(prefix, context);
      this.typography[prefix] = typographyControls(prefix, context);
    }
  }

  // Shows a palette in Project → Colors, where palettes are edited.
  #openPalette(value) {
    this.paletteManager.select(value);
    $("tab-colors").click();
    $("project-settings").showModal();
    $("palette-editor").scrollIntoView({ block: "start" });
  }

  // An appearance edit redraws the inspector before it is recorded.
  restyled(label) {
    this.refresh();
    this.changed(label);
  }

  #reset(scope, group, key, options) {
    const { state } = this.editor;
    if (key) {
      state.resetColor(key, scope, options);
      this.restyled("Reset color");
      return;
    }
    if (group === "palette") state.resetPalette(scope);
    else if (group === "background") state.resetBackground(scope, options);
    else state.resetStyleGroup(group, scope);
    this.restyled(`Reset ${GROUP_NAMES[group]}`);
  }

  #createStyleEditor(prefix, appearance) {
    const scope = scopeOf(prefix),
      { onStart, onEnd } = this.editSession;
    return appearanceControls(prefix, {
      schema: this.schema,
      appearance,
      change: (group, key, value) => {
        this.editor.state.setStyleOption(group, key, value, scope);
        this.restyled(EDIT_NAMES[group]);
      },
      reset: (group, key, options) => this.#reset(scope, group, key, options),
      editSession: { onStart: (label) => onStart(label || COLOR_EDIT_LABELS[prefix]), onEnd },
    });
  }

  #listenSeed(prefix) {
    const scope = scopeOf(prefix),
      seed = $(`${prefix}seed`);
    seed.addEventListener("input", () => {
      if (!seed.value.trim()) return;
      this.editor.state.setStyle("seed", seed.value, scope);
      this.restyled("Change seed");
    });
    $(`${prefix}random-seed`).addEventListener("click", () => {
      this.editor.state.setStyle("seed", crypto.randomUUID().slice(0, 8), scope);
      this.restyled("New pattern seed");
    });
  }

  #styleChoices(prefix, style, targets) {
    for (const key of STYLE_CHOICES) {
      const id = prefix + key,
        values = this.schema.$defs[key].enum;
      const choose = (value) => {
        this.editor.state.setStyle(key, value, scopeOf(prefix));
        this.restyled(`Change ${words(key)}`);
        $(id).querySelector(`input[value="${value}"]`)?.focus();
      };
      const offered = key === "layout" ? layoutChoices(values, style.layout, targets) : values;
      choices(id, offered, style[key], choose, optionLabel);
    }
  }

  // The window frame color applies only to Mac screenshots shown in an app window.
  #showsWindowFrame(prefix, targets) {
    if (prefix) return targets.some((target) => target.platform === "mac");
    return this.#previewTarget.platform === "mac";
  }

  // An "Image only" slide shows the screenshot alone, so its appearance is read-only.
  #refreshScope(prefix, targets) {
    const { state } = this.editor;
    const scope = scopeOf(prefix),
      style = state.styleOf(scope);
    const imageOnly = !prefix && style.layout === "raw";
    this.#styleChoices(prefix, style, targets);
    $(`${prefix}seed`).value = style.seed;
    $(`${prefix}pattern-value`).textContent = title(style.pattern);
    $(`${prefix}seed-settings`).hidden = style.pattern === "none";
    this.styleEditors[prefix].update(style, state.ownStyle(scope), imageOnly, {
      showWindowFrame: this.#showsWindowFrame(prefix, targets),
    });
    this.palettes[prefix].update(imageOnly);
    this.layouts[prefix].update(imageOnly);
    this.typography[prefix].update(imageOnly);
    for (const key of [
      "pattern",
      "deviceFrame",
      "screenshotFit",
      "labelStyle",
      "seed",
      "random-seed",
    ])
      $(prefix + key).disabled = imageOnly;
  }

  #refreshSlide() {
    const { state } = this.editor;
    const imageOnly = state.style.layout === "raw";
    for (const [id] of TEXT_INPUTS) $(id).disabled = imageOnly;
    const overridden = Object.keys(state.ownStyle("slide")).length > 0;
    $("reset-style").disabled = !overridden;
    $("style-scope").textContent = overridden
      ? "This slide overrides project appearance in every language and variant."
      : "Follows the project appearance. Changes here apply to this slide only.";
    const layout = resolvedLayout(state.style.layout, this.#previewTarget);
    $("device-settings").hidden = !["device-top", "device-focus"].includes(layout);
    $("default-device-settings").hidden = ["raw", "window-top"].includes(state.defaultStyle.layout);
  }

  refresh() {
    const targets = this.editor.state.project.targets.map(this.targetOf);
    for (const prefix of PREFIXES) this.#refreshScope(prefix, targets);
    this.#refreshSlide();
    this.paletteManager.update();
    this.layoutLibrary.update();
  }

  #chooseAsset() {
    const path = $("existing-asset").value;
    if (!path) return;
    this.editor.state.setAsset(this.#previewTarget.platform, path);
    this.refreshAsset();
    this.changed("Change screenshot");
  }

  // The screenshot of the platform the canvas previews; switch Size to edit another platform's.
  refreshAsset() {
    const { state, assets } = this.editor,
      platform = this.#previewTarget.platform;
    const current = state.assetPath(platform);
    $("asset-platform").textContent = platformName(platform);
    $("asset-name").textContent = `Used by every ${platformName(platform)} size of this slide.`;
    const known = assets.find((item) => [item.path, `./${item.path}`].includes(current));
    $("existing-asset").replaceChildren(
      new Option("Choose a project image…", ""),
      ...assets.map((item) => new Option(item.name, item.path)),
    );
    $("existing-asset").value = known ? known.path : "";
    $("existing-asset").disabled = !assets.length;
  }
}
