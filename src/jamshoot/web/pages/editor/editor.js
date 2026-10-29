// The editor page: wires the panels, history and actions; Python validates and renders.
import { Inspector, optionLabel, TEXT_INPUTS } from "../../features/appearance/inspector.js";
import { FontLibrary, renderProjectFonts } from "../../features/appearance/typography.js";
import { onUnitChange } from "../../features/appearance/units.js";
import { GuideOverlay, guideKey } from "../../features/preview/guides.js";
import { Preview } from "../../features/preview/preview.js";
import {
  customSizeForm,
  platformList,
  platformMenu,
  sizeText,
} from "../../features/project-settings/platform-list.js";
import { projectLists } from "../../features/project-settings/project-lists.js";
import { updateSlideList } from "../../features/slides/slides.js";
import { createAPI } from "../../shared/api.js";
import { $ } from "../../shared/lib/dom.js";
import { title } from "../../shared/lib/text.js";
import { DraftHistory } from "../../shared/model/history.js";
import { platformName } from "../../shared/model/platforms.js";
import { EditorState, editorRules, findTarget } from "../../shared/model/project.js";
import { dialogBehavior, tabList } from "../../shared/ui/dialogs/dialogs.js";
import { options } from "../../shared/ui/select/options.js";
import { enhanceSelect } from "../../shared/ui/select/select.js";
import { panelController } from "./panels.js";
import { editorShortcut } from "./shortcuts.js";

const meta = (name) => document.querySelector(`meta[name="${name}"]`).content;
const request = createAPI(meta("jamshoot-token"));
const projectAPI = meta("jamshoot-api");
const api = (path, ...rest) => request(projectAPI + path, ...rest);
const panels = panelController();

// Shared with the inspector and the preview: the draft and the project's images.
const editor = { state: null, assets: [] };
// Color pickers record one history step per edit session.
const editSession = {
  onStart: (label) => edits.beginGroup(label || "Edit color"),
  onEnd: () => {
    edits.endGroup();
    historyButtons();
  },
};
const targetOf = (id) => findTarget(catalog, id);
const fonts = new FontLibrary(api, () => {
  preview.forgetPlan();
  renderProjectFonts($("project-fonts"), fonts.families.project);
  $("font-count").textContent = fonts.families.project.length;
  if (editor.state) inspector.refresh();
});
const inspector = new Inspector(editor, { targetOf, changed, editSession, fonts });
const preview = new Preview(editor, {
  api,
  status: (message, error) => status(message, error, false),
  onThumbnail: () => renderSlides(),
  describe: (item) => `${item.variant} · ${optionLabel(item.layout)} · ${title(item.pattern)}`,
  onGuides: () => guides.setGuides(preview.guides),
});
const guides = new GuideOverlay($("preview"));
onUnitChange(() => inspector.refresh());
const lists = projectLists({
  getState: () => editor.state,
  change: (transform, label) => {
    if (busy) throw new Error("Wait for the current operation to finish.");
    checkJSON();
    transform(editor.state);
    refreshControls();
    changed(label);
    status(`${label}: done.`);
  },
  undo: () => restoreHistory("undo"),
});
let bulkPlatform, catalog, revision, savedProject, toastTimer, uploadBytes;
let dirty = false,
  jsonDirty = false,
  busy = false;
// Empty until the first load, so Undo and Redo start disabled.
let edits = new DraftHistory(null, {});

// Disabled while a save, export, upload or load is running.
const LOCKED = [
  "controls",
  "project-controls",
  "slide-controls",
  "save",
  "save-project",
  "open-project",
  "export",
  "reload",
  "locale",
  "target",
  "variant",
];
const RESTORED = { undo: "Undid", redo: "Redid" };
const JSON_PENDING = "Apply your Project JSON changes before Save, Export or Undo/Redo.";
for (const id of ["locale", "variant", "target", "existing-asset", "add-platform"])
  enhanceSelect($(id));

function status(message, error = false, persistent = true) {
  $("status").textContent = message;
  $("status").classList.toggle("error", error);
  if (!error || !persistent) return;
  clearErrors();
  const alert = $("project-settings").open ? $("project-error") : $("canvas-error");
  alert.textContent = message;
  alert.hidden = false;
}

function clearErrors() {
  for (const id of ["project-error", "canvas-error"]) {
    $(id).textContent = "";
    $(id).hidden = true;
  }
}

function savedState(message) {
  for (const id of ["saved-state", "project-saved-state"]) $(id).textContent = message;
  $("saved-state").classList.toggle("is-dirty", message !== "Saved to disk");
}

function refreshDirty() {
  dirty = JSON.stringify(editor.state.project) !== savedProject;
  savedState(jsonDirty ? "JSON changes not applied" : dirty ? "Unsaved changes" : "Saved to disk");
}

function syncJSON() {
  if (!jsonDirty) $("project-json").value = JSON.stringify(editor.state.project, null, 2);
}

function historyButtons() {
  for (const direction of ["undo", "redo"]) {
    const { enabled, title: hint } = edits.control(direction);
    for (const id of [direction, `project-${direction}`]) {
      $(id).disabled = busy || !enabled;
      $(id).title = hint;
    }
  }
}

function changed(label = "Edit project") {
  lists.clearNotice();
  refreshPlatforms();
  refreshMissingScreenshot();
  edits.record(editor.state.project, editor.state.selection, label);
  refreshDirty();
  historyButtons();
  syncJSON();
  renderSlides();
  preview.schedule();
}

// The size the canvas previews; the screenshot section edits its platform's screenshot.
const previewPlatform = () => targetOf(editor.state.selection.target).platform;

function selectSlide(id) {
  if (busy) return;
  clearErrors();
  editor.state.select("slide", id);
  edits.select(editor.state.selection);
  refreshControls();
  preview.schedule(false, { navigated: true });
  if (panels.isNarrow()) panels.close();
}

function slideButtonTitle(id, full) {
  if (full) return `Projects have at most ${editor.state.limitOf("slides")} slides`;
  return id === "add-slide" ? "Add a new slide after this one" : "Duplicate slide";
}

function renderSlides() {
  const { state } = editor,
    slides = state.project.slides;
  updateSlideList(
    $("slides"),
    slides,
    state.selection,
    preview.thumbnails,
    selectSlide,
    preview.loading,
  );
  // Thumbnails follow the previewed size, within a readable range for the panel.
  const target = targetOf(state.selection.target);
  $("slides").style.setProperty(
    "--thumb-aspect",
    String(Math.max(0.8, Math.min(1.8, target.width / target.height))),
  );
  $("slide-count").textContent = `${slides.length}/${state.limitOf("slides")}`;
  const full = state.isFull("slides"),
    index = slides.indexOf(state.slide);
  for (const id of ["add-slide", "duplicate-slide"]) {
    $(id).disabled = full;
    $(id).title = slideButtonTitle(id, full);
  }
  $("remove-slide").disabled = slides.length <= 1;
  $("move-up").disabled = index === 0;
  $("move-down").disabled = index === slides.length - 1;
}

// Writes a field unless it has focus, so typing is never overwritten.
function setField(id, value = "") {
  if (document.activeElement !== $(id)) $(id).value = value;
}

function headlineValidity() {
  const valid = Boolean($("headline").value.trim());
  if (valid) $("headline").removeAttribute("aria-invalid");
  else $("headline").setAttribute("aria-invalid", "true");
  $("headline-error").hidden = valid;
  return valid;
}

function targetLabel(id) {
  const target = targetOf(id);
  return `${platformName(target.platform)} · ${sizeText(target)}`;
}

// Applies one change to the project's platforms and sizes and records it as one history step.
function editTargets(label, transform) {
  transform(editor.state);
  refreshControls();
  changed(label);
}

function openCustomSize() {
  const editorBox = $("custom-size-editor");
  customSizeForm(editorBox, {
    sides: catalog.customSides,
    maxPixels: catalog.customMaxPixels,
    onAdd: (width, height) =>
      editTargets("Add custom size", (state) => state.addCustomSize(width, height)),
    onClose: () => {
      editorBox.hidden = true;
      editorBox.replaceChildren();
    },
  });
}

// Each toolbar select ends with a way to add more, so one option is never a dead end.
const ADD_ACTIONS = {
  locale: ["Add language…", () => $("new-locale").click()],
  variant: ["Add variant…", () => $("new-variant").click()],
  target: ["Add platform or size…", () => enhanceSelect($("add-platform")).open()],
};

// The project's sizes grouped under their platform, each shown as "Mac · 1280 × 800" when chosen.
function sizeOptions() {
  const groups = new Map();
  for (const id of editor.state.project.targets) {
    const target = targetOf(id);
    if (!groups.has(target.platform)) {
      const group = document.createElement("optgroup");
      group.label = platformName(target.platform);
      groups.set(target.platform, group);
    }
    const option = new Option(sizeText(target), id);
    option.dataset.trigger = targetLabel(id);
    groups.get(target.platform).append(option);
  }
  return [...groups.values()];
}

function contextOptions(id, items, selected, label) {
  if (label) options(id, items, selected, label);
  else $(id).replaceChildren(...items);
  const add = new Option(ADD_ACTIONS[id][0], "add:");
  add.dataset.action = "add";
  $(id).append(add);
  $(id).value = selected;
  $(id).disabled = busy;
}
function openAddAction(id) {
  $(id).value = editor.state.selection[id];
  $("project-settings").showModal();
  $("tab-general").click();
  ADD_ACTIONS[id][1]();
}

function refreshContext() {
  const { state } = editor;
  contextOptions("locale", state.project.locales, state.selection.locale, (value) => value);
  const variants = state.variants.map((item) => item.id);
  contextOptions("variant", variants, state.selection.variant, title);
  contextOptions("target", sizeOptions(), state.selection.target);
  lists.update();
}

// The canvas says when the previewed slide still lacks this size's screenshot.
function refreshMissingScreenshot() {
  const { state } = editor,
    platform = previewPlatform();
  $("missing-screenshot").hidden = Boolean(state.assetPath(platform));
  $("missing-screenshot-text").textContent =
    `This slide has no ${platformName(platform)} screenshot yet. Drop an image here or upload one.`;
}

function refreshPlatforms() {
  const { state } = editor;
  const context = {
    catalog,
    targetOf,
    selected: state.project.targets,
    missing: (platform) => state.missingScreenshots(platform),
    onAddSize: (id) => editTargets("Add size", (draft) => draft.addTarget(id)),
    onRemoveSize: (id) =>
      editTargets(`Remove ${targetLabel(id)}`, (draft) => draft.removeTarget(id)),
    onCustom: openCustomSize,
    onAddScreenshots: (platform) => {
      bulkPlatform = platform;
      $("bulk-upload").click();
    },
  };
  platformList($("target-options"), context);
  platformMenu($("add-platform"), context);
}
$("add-platform").addEventListener("change", () => {
  const platform = $("add-platform").value;
  if (platform === "custom") openCustomSize();
  else if (platform)
    editTargets(`Add ${platformName(platform)}`, (state) => state.addPlatform(platform, catalog));
});

function refreshControls() {
  const { state } = editor,
    name = state.project.project.name;
  $("project-name").textContent = name;
  document.title = `${name} · JamShoot Studio`;
  setField("project-title", name);
  $("active-slide").textContent = state.slideName;
  setField("slide-name", state.slide.name);
  refreshContext();
  const copy = state.slide.copy[state.selection.locale];
  for (const [id, key] of TEXT_INPUTS) setField(id, copy[key]);
  headlineValidity();
  $("text-locale").textContent = state.selection.locale;
  inspector.refreshAsset();
  refreshPlatforms();
  refreshMissingScreenshot();
  inspector.refresh();
  renderSlides();
  syncJSON();
}

function unlock() {
  busy = false;
  $("editor").removeAttribute("aria-busy");
  historyButtons();
  const { state } = editor;
  for (const id of LOCKED) $(id).disabled = !state;
  if (!state) return;
  if (preview.pending) preview.schedule(true);
}

async function action(callback) {
  if (busy) return;
  busy = true;
  clearErrors();
  preview.cancel();
  historyButtons();
  $("editor").setAttribute("aria-busy", "true");
  for (const id of LOCKED) $(id).disabled = true;
  try {
    await callback();
  } catch (error) {
    status(error.message, true);
    showLoadFailure();
  } finally {
    unlock();
  }
}

function showLoadFailure() {
  $("retry-project").hidden = Boolean(editor.state);
  if (editor.state) return;
  $("empty-preview").hidden = true;
  $("project-name").textContent = "Could not open project";
  savedState("Project unavailable");
}

function toast(message) {
  $("toast").textContent = message;
  $("toast").hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => {
    $("toast").hidden = true;
  }, 6000);
}

async function load() {
  $("retry-project").hidden = true;
  if (!editor.state) {
    $("empty-preview").hidden = false;
    $("project-name").textContent = "Opening project…";
  }
  const snapshot = await api("/project");
  editor.assets = (await api("/assets")).assets;
  ({ catalog, revision } = snapshot);
  uploadBytes = snapshot.limits.uploadBytes;
  inspector.load(snapshot);
  if (editor.state) editor.state.replace(snapshot.project);
  else editor.state = new EditorState(snapshot.project, editorRules(snapshot));
  edits = new DraftHistory(editor.state.project, editor.state.selection);
  savedProject = JSON.stringify(editor.state.project);
  preview.dropThumbnails();
  jsonDirty = false;
  refreshDirty();
  $("output-path").textContent = snapshot.output;
  refreshControls();
  status("Project loaded.");
  preview.schedule();
  historyButtons();
}

function checkJSON() {
  if (jsonDirty) throw new Error(JSON_PENDING);
  if (!headlineValidity())
    throw new Error("Enter a headline before saving or exporting. Your other edits are kept.");
}

function canRestore() {
  if (busy) return false;
  if (jsonDirty) status(JSON_PENDING, true);
  return !jsonDirty;
}

function restoreHistory(direction) {
  if (!canRestore()) return;
  const step = edits.step(direction);
  if (!step) return;
  lists.clearNotice();
  editor.state.selection = step.selection;
  editor.state.replace(step.project);
  refreshDirty();
  refreshControls();
  historyButtons();
  preview.schedule(true);
  status(`${RESTORED[direction]}: ${step.label}`);
}
for (const prefix of ["", "project-"])
  for (const direction of ["undo", "redo"])
    $(prefix + direction).addEventListener("click", () => restoreHistory(direction));

const COMMANDS = {
  save: () => $("save").click(),
  undo: () => restoreHistory("undo"),
  redo: () => restoreHistory("redo"),
};
function historyShortcut(event) {
  const command = editorShortcut(event);
  if (!command || document.querySelector(".color-picker-dialog:modal")) return;
  event.preventDefault();
  COMMANDS[command]();
}
document.addEventListener("keydown", historyShortcut);
$("project-settings").addEventListener("keydown", historyShortcut);

// Typing in one field is one history step, named after the field's label.
function historyField(target) {
  return (
    target.matches('textarea,input[type="number"],input[type="range"],input:not([type])') &&
    !target.closest(".color-picker-dialog") &&
    target.id !== "project-json"
  );
}
const fieldLabel = (target) => target.labels?.[0]?.textContent || "field";
document.addEventListener("focusin", (event) => {
  if (historyField(event.target)) edits.beginGroup(`Edit ${fieldLabel(event.target)}`);
});
document.addEventListener("focusout", (event) => {
  if (!historyField(event.target)) return;
  edits.endGroup();
  historyButtons();
});

$("open-project").addEventListener("click", () => $("project-settings").showModal());
dialogBehavior($("project-settings"));
for (const id of ["close-project", "done-project"])
  $(id).addEventListener("click", () => $("project-settings").close());
tabList($("project-tabs"), (tab) => {
  $("project-settings").scrollTo({ top: 0 });
  if (tab.id === "tab-typography") fonts.load().catch((error) => status(error.message, true));
});
// A font goes into the project's assets/fonts; slides that name its family render with it.
$("font-upload").addEventListener("change", () => {
  const [file] = $("font-upload").files;
  $("font-upload").value = "";
  if (!file) return;
  action(async () => {
    if (file.size > uploadBytes)
      throw new Error(`Font must be at most ${uploadBytes / 1048576} MiB.`);
    await fonts.load();
    const added = await fonts.upload(file);
    preview.schedule();
    status(`Added ${added.join(", ") || file.name} to the project's fonts.`);
  });
});

$("project-title").addEventListener("input", () => {
  const { project } = editor.state;
  if (!$("project-title").value.trim()) return;
  project.project.name = $("project-title").value;
  $("project-name").textContent = project.project.name;
  changed("Rename project");
});
$("project-title").addEventListener("change", () => {
  $("project-title").value = editor.state.project.project.name;
});
$("slide-name").addEventListener("change", () => {
  const { state } = editor;
  state.setSlideName($("slide-name").value);
  $("slide-name").value = state.slide.name || "";
  $("active-slide").textContent = state.slideName;
  changed("Rename slide");
});
for (const id of ["locale", "target", "variant"])
  $(id).addEventListener("change", () => {
    if ($(id).value === "add:") {
      openAddAction(id);
      return;
    }
    editor.state.select(id, $(id).value);
    edits.select(editor.state.selection);
    refreshControls();
    preview.schedule(false, { navigated: true });
  });
for (const [id, key] of TEXT_INPUTS)
  $(id).addEventListener("input", () => {
    if (key === "headline") {
      headlineValidity();
      clearErrors();
    }
    editor.state.setFieldText(key, $(id).value);
    changed("Edit text");
  });

$("project-json").addEventListener("input", () => {
  jsonDirty = true;
  savedState("JSON changes not applied");
});
$("apply-json").addEventListener("click", () =>
  action(async () => {
    const text = $("project-json").value;
    // Validate the original bytes before JSON.parse can discard duplicate keys.
    try {
      await api("/plan", `{"project":${text}}`, { serialized: true });
    } catch (error) {
      $("project-json").setAttribute("aria-invalid", "true");
      throw error;
    }
    $("project-json").removeAttribute("aria-invalid");
    editor.state.replace(JSON.parse(text));
    jsonDirty = false;
    refreshControls();
    changed("Apply JSON");
  }),
);
for (const id of ["save", "save-project"])
  $(id).addEventListener("click", () =>
    action(async () => {
      checkJSON();
      const { project } = editor.state;
      revision = (await api("/project", { project, revision })).revision;
      savedProject = JSON.stringify(project);
      refreshDirty();
      status("Project saved.");
    }),
  );
$("reload").addEventListener("click", () => {
  if ((!dirty && !jsonDirty) || window.confirm("Discard unsaved edits and reload from disk?"))
    action(load);
});
$("export").addEventListener("click", () =>
  action(async () => {
    checkJSON();
    status("Exporting all screenshots…");
    const manifest = await api("/export", { project: editor.state.project });
    $("output-path").textContent = manifest.outputDirectory;
    status(`Exported ${manifest.fileCount} PNG files and manifest.json.`);
    toast(`${manifest.fileCount} PNG files exported to ${manifest.outputDirectory}`);
  }),
);
// Stores one image in the project, named after its file, and returns its path.
async function uploadImage(file) {
  if (file.size > uploadBytes)
    throw new Error(`Screenshot must be at most ${uploadBytes / 1048576} MiB.`);
  const name = encodeURIComponent(file.name);
  return (await api(`/assets?name=${name}`, file, { raw: true })).path;
}
// Makes `file` this slide's screenshot for the platform the canvas previews.
function setScreenshot(file) {
  return action(async () => {
    const path = await uploadImage(file);
    editor.assets = (await api("/assets")).assets;
    editor.state.setAsset(previewPlatform(), path);
    refreshControls();
    changed("Upload screenshot");
    status(`${platformName(previewPlatform())} screenshot added to ${editor.state.slideName}.`);
  });
}
$("upload").addEventListener("change", () => {
  const [file] = $("upload").files;
  $("upload").value = "";
  if (file) setScreenshot(file);
});

// Dropping an image on the canvas sets the previewed slide's screenshot.
const workspace = $("workspace");
workspace.addEventListener("dragover", (event) => {
  if (busy || !event.dataTransfer?.types.includes("Files")) return;
  event.preventDefault();
  workspace.classList.add("is-dropping");
});
workspace.addEventListener("dragleave", (event) => {
  if (!workspace.contains(event.relatedTarget)) workspace.classList.remove("is-dropping");
});
workspace.addEventListener("drop", (event) => {
  workspace.classList.remove("is-dropping");
  const [file] = event.dataTransfer?.files || [];
  if (!file) return;
  event.preventDefault();
  setScreenshot(file);
});

// One image per slide that lacks the platform's screenshot, in slide and file name order.
$("bulk-upload").addEventListener("change", () =>
  action(async () => {
    const files = [...$("bulk-upload").files].sort((a, b) =>
      a.name.localeCompare(b.name, undefined, { numeric: true }),
    );
    try {
      const paths = [];
      for (const file of files) paths.push(await uploadImage(file));
      editor.assets = (await api("/assets")).assets;
      const added = editor.state.addScreenshots(bulkPlatform, paths);
      refreshControls();
      changed("Add screenshots");
      toast(`Added ${added} ${platformName(bulkPlatform)} screenshot${added === 1 ? "" : "s"}.`);
    } finally {
      $("bulk-upload").value = "";
    }
  }),
);
$("upload-missing").addEventListener("click", () => $("upload").click());

const SLIDE_ACTIONS = {
  "add-slide": [(state) => state.addSlide(), "Add slide"],
  "duplicate-slide": [(state) => state.duplicateSlide(), "Duplicate slide"],
  "remove-slide": [(state) => state.removeSlide(), "Delete slide"],
  "move-up": [(state) => state.moveSlide(-1), "Move slide"],
  "move-down": [(state) => state.moveSlide(1), "Move slide"],
};
// A new slide puts focus on its headline; other actions keep it on the selected card.
function focusAfterSlideAction(id) {
  if (id !== "add-slide") {
    $("slides").querySelector(`[data-slide="${editor.state.selection.slide}"]`)?.focus();
    return;
  }
  if ($("inspector-panel").hidden) $("toggle-inspector-panel").click();
  $("headline").focus();
  $("headline").select();
}
for (const [id, [transform, label]] of Object.entries(SLIDE_ACTIONS))
  $(id).addEventListener("click", () => {
    transform(editor.state);
    preview.dropThumbnails(new Set(editor.state.project.slides.map((slide) => slide.id)));
    refreshControls();
    changed(label);
    focusAfterSlideAction(id);
  });
window.addEventListener("beforeunload", (event) => {
  if (!dirty && !jsonDirty) return;
  event.preventDefault();
  event.returnValue = "";
});
$("retry-project").addEventListener("click", () => action(load));
$("retry-preview").addEventListener("click", () => preview.schedule());
action(load);

// Hovering, focusing or dragging a spacing or text setting in the slide panel shows the
// guides it changes on the canvas.
let hoveredGuide = null,
  focusedGuide = null;
function guideFrom(target) {
  const row = target?.closest?.("#layout-settings .range-control, #typography .range-control");
  const number = row?.querySelector('input[type="number"]');
  return number ? guideKey(number.id, inspector.typography[""].field) : null;
}
function showGuide() {
  guides.setActive(hoveredGuide ?? focusedGuide);
}
$("controls").addEventListener("pointerover", (event) => {
  hoveredGuide = guideFrom(event.target);
  showGuide();
});
$("controls").addEventListener("pointerleave", () => {
  hoveredGuide = null;
  showGuide();
});
$("controls").addEventListener("focusin", (event) => {
  focusedGuide = guideFrom(event.target);
  showGuide();
});
$("controls").addEventListener("focusout", () => {
  focusedGuide = null;
  showGuide();
});
