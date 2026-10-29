// Palettes as cards, and per scope: which palette the colors follow and what to do with changes.

import { $ } from "../../shared/lib/dom.js";
import { title } from "../../shared/lib/text.js";
import { paletteEntry } from "../../shared/model/project.js";
import { cssGradient } from "../../shared/ui/color-picker/color.js";
import { enhanceSelect } from "../../shared/ui/select/select.js";

const scopeOf = (prefix) => (prefix ? "project" : "slide");

// One radio card: the palette's fill with its pattern and text colors on top, and its name.
function paletteCard(group, { value, name, colors, gradient, tag }) {
  const card = document.createElement("label"),
    radio = document.createElement("input");
  const swatch = document.createElement("span"),
    caption = document.createElement("span");
  card.className = "palette-card";
  card.title = tag ? `${name} (${tag})` : name;
  radio.type = "radio";
  radio.name = group;
  radio.value = value;
  swatch.className = "palette-swatch";
  swatch.style.background = cssGradient(colors, gradient);
  for (const key of ["accent", "text", "muted"]) {
    const chip = document.createElement("span");
    chip.style.background = colors[key];
    swatch.append(chip);
  }
  if (tag) {
    const badge = document.createElement("small");
    badge.className = "palette-tag";
    badge.textContent = tag;
    swatch.append(badge);
  }
  caption.className = "palette-name";
  caption.textContent = name;
  card.append(radio, swatch, caption);
  return card;
}

// Card data for the project's palettes and the starters, gradients completed with defaults.
export function paletteSections(state, appearance) {
  const complete = (gradient) => ({ ...appearance.gradientDefaults, ...gradient });
  const defaultValue = state.paletteValue("project");
  const item = (value, name, entry) => ({
    value,
    name,
    colors: entry.colors,
    gradient: complete(entry.gradient),
    tag: value === defaultValue ? "Default" : "",
  });
  return [
    [
      "Project palettes",
      (state.project.colorStyles || []).map((style) =>
        item(`style:${style.id}`, style.name, style),
      ),
    ],
    [
      "Starter palettes",
      Object.entries(appearance.starterPalettes).map(([id, colors]) =>
        item(`starter:${id}`, title(id), { colors }),
      ),
    ],
  ].filter(([, items]) => items.length);
}

// Fills the radio group `container` (a fieldset) with headed card sections and checks `value`.
// Rebuilt only when the cards change, so focus stays on the chosen card.
export function renderPaletteCards(container, sections, value) {
  const signature = JSON.stringify(sections);
  if (container.dataset.signature !== signature) {
    container.dataset.signature = signature;
    const items = sections.flatMap(([label, cards]) => {
      const elements = cards.map((card) => paletteCard(container.id, card));
      if (!label) return elements;
      const heading = document.createElement("p");
      heading.className = "palette-group";
      heading.textContent = label;
      return [heading, ...elements];
    });
    container.replaceChildren(...container.querySelectorAll(":scope > legend"), ...items);
  }
  for (const radio of container.querySelectorAll("input")) radio.checked = radio.value === value;
}

// The palette the scope's colors are based on, by name; null for colors set only here.
function baseName(state, value) {
  if (value.startsWith("style:"))
    return state.project.colorStyles.find((style) => `style:${style.id}` === value)?.name;
  if (value.startsWith("starter:")) return title(value.slice("starter:".length));
  return null;
}

function changedPaletteStatus(scope, changes, name) {
  const where = scope === "project" ? "in the project default" : "on this slide";
  return `${changes} ${changes === 1 ? "change" : "changes"} to “${name}” ${where}.`;
}

function paletteStatus(scope, changes, name) {
  if (!name) return "Colors set here only. Save them as a palette to reuse them.";
  if (changes) return changedPaletteStatus(scope, changes, name);
  // The slide's select already names its palette.
  return scope === "project" ? `Slides that follow the project use “${name}”.` : "";
}

// A palette's mark in a select: a circle cut on the slant into two broad bands, its
// background and its headline color.
function paletteMark(colors, gradient) {
  return `linear-gradient(-45deg, ${colors.text} 0 50%, transparent 50%), ${cssGradient(colors, gradient)}`;
}

function paletteOption({ value, name, colors, gradient }, detail) {
  const option = new Option(name, value);
  option.dataset.swatch = paletteMark(colors, gradient);
  if (detail) option.dataset.detail = detail;
  return option;
}

// The slide's palette choices: the project default (named by its palette), colors set only on
// the slide, then the project's and the starter palettes in groups.
function pickerOptions(state, appearance, value, own) {
  const complete = (gradient) => ({ ...appearance.gradientDefaults, ...gradient });
  const project = paletteEntry(appearance, state.defaultStyle);
  const items = [
    paletteOption(
      { value: "", name: "Project default", ...project, gradient: complete(project.gradient) },
      baseName(state, state.paletteValue("project")),
    ),
  ];
  if (value === "custom")
    items.push(
      paletteOption({ value, name: "Custom colors", ...own, gradient: complete(own.gradient) }),
    );
  for (const [label, cards] of paletteSections(state, appearance)) {
    const group = document.createElement("optgroup");
    group.label = label;
    group.append(...cards.map((card) => paletteOption(card, card.tag)));
    items.push(group);
  }
  return items;
}

// Replaces the select's options only when they change, so an open menu is not rebuilt.
function renderOptions(select, items) {
  const signature = items.map((item) => item.outerHTML).join("");
  if (select.dataset.signature === signature) return;
  select.dataset.signature = signature;
  select.replaceChildren(...items);
}

// The project palette `value` names, or null for a starter.
function savedPalette(state, value) {
  if (!value.startsWith("style:")) return null;
  return state.project.colorStyles.find((style) => `style:${style.id}` === value);
}

// The overrides' summary counts them; the first change opens them, afterwards the person decides.
function showChanges(details, changes, hadChanges) {
  if (changes && !hadChanges) details.open = true;
  const badge = details.querySelector("summary .badge");
  badge.hidden = !changes;
  badge.textContent = String(changes);
}

// The slide's (prefix "") or project's ("default-") palette: a card grid for the slide,
// a status line, update/save/edit actions and the collapsible overrides.
// `openManager(value)` shows that palette in Project → Colors.
export function paletteControl(prefix, { getState, appearance, changed, openManager }) {
  const scope = scopeOf(prefix);
  const picker = document.getElementById(`${prefix}palette`),
    save = $(`${prefix}save-palette`),
    apply = $(`${prefix}update-palette`),
    edit = $(`${prefix}edit-palette`),
    details = $(`${prefix}customize-colors`);
  let notice = "",
    linked = null,
    target = "",
    hadChanges = false;
  if (picker) enhanceSelect(picker);
  picker?.addEventListener("change", () => {
    notice = "";
    getState().setPalette(scope, picker.value);
    changed(picker.value ? "Choose palette" : "Use project palette");
  });
  const entry = () => paletteEntry(appearance, getState().styleOf(scope));
  save.addEventListener("click", () => {
    const state = getState(),
      name = state.nextStyleName("palette");
    state.saveSavedStyle("palette", name, entry(), scope);
    notice = `Saved as “${name}”. Rename it in Project → Colors.`;
    changed("Save palette");
  });
  // Folds the scope's changes into the linked palette, for every slide that uses it.
  apply.addEventListener("click", () => {
    const state = getState();
    state.updateSavedStyle("palette", linked.id, linked.name, entry());
    state.resetPalette(scope);
    notice = `Updated “${linked.name}” everywhere it is used.`;
    changed("Update palette");
  });
  edit.addEventListener("click", () => {
    notice = "";
    openManager(target);
  });
  function updatePicker(state, value, disabled) {
    if (!picker) return;
    renderOptions(picker, pickerOptions(state, appearance, value, entry()));
    picker.value = value;
    picker.disabled = disabled;
  }
  function updateApply(ownLink, changes, disabled) {
    apply.hidden = !(ownLink && changes);
    if (ownLink) apply.lastChild.textContent = `Update “${ownLink.name}”`;
    apply.disabled = disabled;
  }
  function updateSave(state, value, changes, disabled) {
    save.hidden = !changes && value !== "custom";
    save.lastChild.textContent = changes ? "Save as new palette" : "Save as palette";
    save.disabled = disabled || state.isFull("colorStyles");
  }
  function updateStatus(state, changes) {
    if (changes) notice = "";
    $(`${prefix}palette-changes`).classList.toggle("has-changes", changes > 0);
    const status = $(`${prefix}palette-status`);
    status.textContent = notice || paletteStatus(scope, changes, baseName(state, target));
    status.hidden = !status.textContent;
  }
  function update(disabled) {
    const state = getState(),
      value = state.paletteValue(scope),
      own = state.ownStyle(scope),
      changes = Object.keys({ ...own.colors, ...own.gradient }).length;
    updatePicker(state, value, disabled);
    target = value || state.paletteValue("project");
    linked = savedPalette(state, target);
    const ownLink = savedPalette(state, value);
    updateStatus(state, changes);
    updateApply(ownLink, changes, disabled);
    updateSave(state, value, changes, disabled);
    // The project default sits under the palette editor already.
    edit.hidden = !picker || value === "custom";
    edit.disabled = disabled;
    showChanges(details, changes, hadChanges);
    hadChanges = changes > 0;
  }
  return { update };
}
