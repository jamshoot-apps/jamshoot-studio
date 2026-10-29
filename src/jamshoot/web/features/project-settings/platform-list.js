// Project → Platforms and sizes: each platform the project exports with its sizes, and menus to add more.
import { platformName } from "../../shared/model/platforms.js";
import { button } from "../../shared/ui/button/button.js";
import { enhanceSelect } from "../../shared/ui/select/select.js";

const PLATFORMS = ["mac", "iphone", "iphone-duo", "ipad", "custom"];

function element(tag, className, text = "") {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

// "Dynamic Island · medium · Required", for picking among a platform's sizes.
function targetCaption(target, catalog) {
  if (target.platform === "custom") return "Screenshot as is, no device mockup";
  const groups = target.displayGroups.map((id) =>
    catalog.displayGroups.find((group) => group.id === id),
  );
  // A group named after the platform itself, such as "Mac", adds nothing.
  const labels = groups.map((group) => group.label);
  const notes = labels.filter((label) => label !== platformName(target.platform));
  if (notes.length) notes.splice(0, notes.length, notes.join(" / "));
  notes.push(...requirementNotes(groups));
  if (target.statusBar === "excluded") notes.push("No status bar");
  return notes.join(" · ");
}

function requirementNotes(groups) {
  const notes = [];
  if (groups.some((group) => group.required)) notes.push("Required");
  // A dated requirement, such as Duo screenshots for apps built with a newer SDK.
  const from = groups.find((group) => group.requiredFrom);
  if (from) notes.push(`Required from ${from.requiredFrom}: ${from.condition}`);
  return notes;
}

function validatePixels(width, height, maxPixels) {
  if (maxPixels && width * height > maxPixels)
    throw new Error(
      `Use at most ${maxPixels.toLocaleString()} pixels in total. Reduce the width or height.`,
    );
}

export const sizeText = (target) => `${target.width} × ${target.height}`;

// "an iPad", "a Mac".
const withArticle = (name) => `${/^[aeiou]/i.test(name) ? "an" : "a"} ${name}`;

// "Slides 2 and 3", "Slide 1", "Slides 1, 2 and 4".
function slideList(numbers) {
  const names = numbers.map(String);
  const last = names.pop();
  return names.length ? `Slides ${names.join(", ")} and ${last}` : `Slide ${last}`;
}

// An action menu: picking an option calls `onPick` with its value.
function menu(id, placeholder, choices, onPick) {
  const select = document.createElement("select");
  select.id = id;
  select.dataset.menu = "";
  select.dataset.placeholder = placeholder;
  const empty = new Option("", "");
  empty.hidden = true;
  select.append(empty, ...choices);
  select.addEventListener("change", () => select.value && onPick(select.value));
  return select;
}

function sizeRow(target, context) {
  const row = element("li", "platform-size"),
    text = element("span", "platform-size-name", sizeText(target));
  row.dataset.target = target.id;
  text.append(element("small", "detail", targetCaption(target, context.catalog)));
  const remove = button({
    label: `Remove ${platformName(target.platform)} ${sizeText(target)}`,
    icon: "close",
    variant: "quiet",
    iconOnly: true,
    onClick: () => context.onRemoveSize(target.id),
  });
  // A project always exports at least one size.
  remove.disabled = context.selected.length === 1;
  row.append(text, remove);
  return row;
}

function missingNotice(platform, missing, context) {
  const notice = element("div", "platform-missing");
  notice.append(
    element(
      "p",
      "",
      `${slideList(missing)} ${missing.length === 1 ? "needs" : "need"} ${withArticle(platformName(platform))} screenshot.`,
    ),
    button({
      label: "Add screenshots…",
      icon: "cloud-upload",
      size: "sm",
      title: "Choose one image per slide, in slide order",
      onClick: () => context.onAddScreenshots(platform),
    }),
  );
  return notice;
}

// The platform's sizes not in the project yet, or the custom size form for custom sizes.
function addSize(platform, chosen, context) {
  if (platform === "custom")
    return button({
      label: "Add size",
      icon: "add",
      variant: "quiet",
      size: "sm",
      onClick: () => context.onCustom(),
    });
  const free = context.catalog.targets.filter(
    (target) => target.platform === platform && !chosen.includes(target),
  );
  if (!free.length) return null;
  const choices = free.map((target) => {
    const option = new Option(`${sizeText(target)} · ${target.orientation}`, target.id);
    option.dataset.detail = targetCaption(target, context.catalog).split(" · ")[0];
    return option;
  });
  return menu(`add-size-${platform}`, "Add size", choices, context.onAddSize);
}

function platformCard(platform, chosen, context) {
  const card = element("section", "platform-card"),
    sizes = element("ul", "platform-sizes");
  card.dataset.platform = platform;
  card.setAttribute("aria-label", platformName(platform));
  sizes.append(...chosen.map((target) => sizeRow(target, context)));
  card.append(element("h4", "platform-name", platformName(platform)), sizes);
  const missing = context.missing(platform);
  if (missing.length) card.append(missingNotice(platform, missing, context));
  const add = addSize(platform, chosen, context);
  if (add) card.append(add);
  return card;
}

// "Add platform": the platforms the project does not export yet, then a custom size.
export function platformMenu(select, context) {
  const used = new Set(context.selected.map((id) => context.targetOf(id).platform));
  const choices = PLATFORMS.filter((platform) => platform === "custom" || !used.has(platform)).map(
    (platform) =>
      new Option(platform === "custom" ? "Custom size…" : platformName(platform), platform),
  );
  select.replaceChildren(new Option("", ""), ...choices);
  select.options[0].hidden = true;
}

function sideField(id, text, sides) {
  const field = element("div", "custom-size-side"),
    label = element("label", "", text),
    input = document.createElement("input");
  Object.assign(input, {
    id,
    type: "number",
    placeholder: `${sides[0]}–${sides[1]}`,
    step: 1,
  });
  input.inputMode = "numeric";
  label.htmlFor = id;
  field.append(label, input);
  return [field, input];
}

// Width and height of a custom size in pixels; `onAdd(width, height)` throws to show an error.
export function customSizeForm(container, { sides, maxPixels, onAdd, onClose }) {
  const form = element("form", "project-inline-editor custom-size-form"),
    fields = element("div", "custom-size-fields"),
    error = element("p", "project-field-error"),
    actions = element("div", "project-list-actions");
  const [widthField, width] = sideField("custom-width", "Width (px)", sides);
  const [heightField, height] = sideField("custom-height", "Height (px)", sides);
  error.setAttribute("role", "alert");
  error.id = "custom-size-error";
  for (const input of [width, height]) {
    input.required = true;
    input.min = sides[0];
    input.max = sides[1];
    input.setAttribute("aria-describedby", error.id);
    input.addEventListener("input", () => {
      for (const side of [width, height]) side.removeAttribute("aria-invalid");
      error.textContent = "";
    });
  }
  fields.append(widthField, heightField);
  const save = button({ label: "Add size", variant: "primary" });
  save.type = "submit";
  actions.append(save, button({ label: "Cancel", variant: "quiet", onClick: onClose }));
  form.append(fields, error, actions);
  form.addEventListener("submit", (event) => {
    event.preventDefault();
    if (!form.reportValidity()) return;
    try {
      validatePixels(width.valueAsNumber, height.valueAsNumber, maxPixels);
      onAdd(Number(width.value), Number(height.value));
      onClose();
    } catch (failure) {
      error.textContent = failure.message;
      for (const input of [width, height]) input.setAttribute("aria-invalid", "true");
    }
  });
  form.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    event.preventDefault();
    event.stopPropagation();
    onClose();
  });
  container.replaceChildren(form);
  container.hidden = false;
  width.focus();
}

// Platforms with their sizes, slides missing their screenshot and a way to add sizes. Redraws
// only when something shown changes, so an open menu survives unrelated edits. `context`
// holds `catalog`, `targetOf(id)`, the `selected` target ids, `missing(platform)` slide
// numbers and the callbacks `onAddSize(id)`, `onRemoveSize(id)`, `onCustom()` and
// `onAddScreenshots(platform)`.
export function platformList(container, context) {
  const chosen = context.selected.map(context.targetOf);
  const platforms = PLATFORMS.filter((platform) =>
    chosen.some((target) => target.platform === platform),
  );
  const signature = JSON.stringify([context.selected, platforms.map(context.missing)]);
  if (container.dataset.signature === signature) return;
  container.dataset.signature = signature;
  const focused = focusedPlatform();
  container.replaceChildren(
    ...platforms.map((platform) =>
      platformCard(
        platform,
        chosen.filter((target) => target.platform === platform),
        context,
      ),
    ),
  );
  for (const select of container.querySelectorAll("select[data-menu]")) enhanceSelect(select);
  restorePlatformFocus(container, focused);
}

function focusedPlatform() {
  return document.activeElement?.closest("[data-target], [data-platform]")?.dataset;
}

function platformFocus(container, key, value) {
  return value && container.querySelector(`[data-${key}="${value}"] button`);
}

function restorePlatformFocus(container, focused = {}) {
  const again =
    platformFocus(container, "target", focused.target) ||
    platformFocus(container, "platform", focused.platform);
  again?.focus();
}
