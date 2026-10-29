// Start screen: the local project library. Projects open in the editor at /project/<id>.
import { createAPI } from "../../shared/api.js";
import { $ } from "../../shared/lib/dom.js";
import { platformName } from "../../shared/model/platforms.js";
import { button } from "../../shared/ui/button/button.js";
import { dialogBehavior } from "../../shared/ui/dialogs/dialogs.js";
import { icon } from "../../shared/ui/icon/icon.js";

const api = createAPI(document.querySelector('meta[name="jamshoot-token"]').content);
const thumbnails = new Map();
// Why a newly saved Studio folder may not survive the next start.
const SOURCE_NOTES = {
  "--home":
    "This run was started with --home. Saving switches folders now; runs started with --home keep using theirs.",
  JAMSHOOT_HOME:
    "JAMSHOOT_HOME is set. Saving switches folders now; later runs use JAMSHOOT_HOME while it is set.",
};
let projects = [];

function relative(iso) {
  if (!iso) return "";
  const seconds = (Date.now() - new Date(iso).getTime()) / 1000;
  const format = new Intl.RelativeTimeFormat(undefined, { numeric: "auto" });
  for (const [unit, size] of [
    ["year", 31536000],
    ["month", 2592000],
    ["week", 604800],
    ["day", 86400],
    ["hour", 3600],
    ["minute", 60],
  ]) {
    if (Math.abs(seconds) >= size) return format.format(-Math.round(seconds / size), unit);
  }
  return "just now";
}

function showError(message) {
  $("home-error").textContent = message;
  $("home-error").hidden = !message;
}

async function thumbnail(item, frame) {
  if (item.error) return;
  const key = `${item.id}:${item.revision}`;
  try {
    if (!thumbnails.has(key))
      thumbnails.set(key, URL.createObjectURL(await api(`/api/projects/${item.id}/thumbnail`)));
    const image = document.createElement("img");
    image.alt = "";
    image.src = thumbnails.get(key);
    frame.replaceChildren(image);
  } catch (error) {
    frame.replaceChildren(icon("image"));
    frame.title = error.message;
    frame.classList.add("is-missing");
  }
}

function projectSummary(item) {
  const parts = [
    item.platforms.map(platformName).join(", "),
    `${item.slides} ${item.slides === 1 ? "slide" : "slides"}`,
  ];
  if (item.locales > 1) parts.push(`${item.locales} languages`);
  parts.push(`Edited ${relative(item.updatedAt)}`);
  return parts.join(" · ");
}

function card(item) {
  const element = document.createElement("li"),
    link = document.createElement("a"),
    frame = document.createElement("span");
  const body = document.createElement("span"),
    name = document.createElement("strong"),
    meta = document.createElement("small");
  element.className = "project-card";
  link.className = "project-link";
  frame.className = "project-thumb";
  frame.append(icon("image"));
  meta.className = "detail";
  name.textContent = item.name;
  if (item.error) {
    link.removeAttribute("href");
    link.setAttribute("aria-disabled", "true");
    meta.textContent = item.error;
    meta.classList.add("project-error");
  } else {
    link.href = `/project/${item.id}`;
    meta.textContent = projectSummary(item);
  }
  body.className = "project-body";
  body.append(name, meta);
  link.append(frame, body);
  const remove = button({
    label: `Remove ${item.name}`,
    icon: "trash",
    variant: "quiet",
    iconOnly: true,
    title: item.managed ? "Move to Studio trash" : "Remove from list",
  });
  remove.addEventListener("click", async () => {
    const question = item.managed
      ? `Remove “${item.name}”? Its folder moves to the Studio trash and can be restored from there.`
      : `Remove “${item.name}” from the list? Its files stay at ${item.path}.`;
    if (!window.confirm(question)) return;
    try {
      await api(`/api/projects/${item.id}`, undefined, { method: "DELETE" });
      await refresh();
    } catch (error) {
      showError(error.message);
    }
  });
  const actions = document.createElement("span");
  actions.className = "project-actions";
  if (!item.error) actions.append(downloadButton(item));
  actions.append(remove);
  element.append(link, actions);
  element.title = item.path;
  thumbnail(item, frame);
  return element;
}

// The project folder as <id>.zip, ready to import into another Studio.
function downloadButton(item) {
  const download = button({
    label: `Download ${item.name} as .zip`,
    icon: "download",
    variant: "quiet",
    iconOnly: true,
    title: "Download .zip",
  });
  download.addEventListener("click", async () => {
    try {
      const link = document.createElement("a");
      link.href = URL.createObjectURL(await api(`/api/projects/${item.id}/archive`));
      link.download = `${item.id}.zip`;
      link.click();
      setTimeout(() => URL.revokeObjectURL(link.href), 1000);
    } catch (error) {
      showError(error.message);
    }
  });
  return download;
}

async function importArchive(file) {
  if (!file) return;
  if (!file.name.toLowerCase().endsWith(".zip")) {
    showError(`${file.name} is not a .zip archive. Export a project from Studio to import it.`);
    return;
  }
  showError("");
  try {
    const item = await api("/api/projects/import", file, { raw: true });
    location.href = `/project/${item.id}`;
  } catch (error) {
    showError(error.message);
  }
}

// Dropping a file anywhere on the page imports it; the overlay shows while one is dragged.
function dropZone() {
  let depth = 0;
  const carriesFiles = (event) => event.dataTransfer?.types.includes("Files");
  const show = (visible) => {
    $("drop-zone").hidden = !visible;
  };
  addEventListener("dragenter", (event) => {
    if (!carriesFiles(event)) return;
    depth += 1;
    show(true);
  });
  addEventListener("dragleave", () => {
    depth = Math.max(0, depth - 1);
    if (!depth) show(false);
  });
  addEventListener("dragover", (event) => {
    if (carriesFiles(event)) event.preventDefault();
  });
  addEventListener("drop", (event) => {
    if (!carriesFiles(event)) return;
    event.preventDefault();
    depth = 0;
    show(false);
    importArchive(event.dataTransfer.files[0]);
  });
}

function render() {
  const query = $("project-search").value.trim().toLocaleLowerCase();
  const visible = projects.filter((item) => item.name.toLocaleLowerCase().includes(query));
  $("projects").replaceChildren(...visible.map(card));
  $("projects").hidden = !projects.length;
  $("empty-projects").hidden = projects.length > 0;
  $("no-results").hidden = !projects.length || visible.length > 0;
  $("project-search").hidden = projects.length < 6 && !query;
}

async function refresh() {
  $("home-loading").hidden = false;
  $("retry-projects").hidden = true;
  $("projects").setAttribute("aria-busy", "true");
  try {
    const result = await api("/api/projects");
    projects = result.projects;
    $("home-path").textContent = `Stored in ${result.home}`;
    showError("");
    render();
  } catch (error) {
    showError(error.message);
    $("retry-projects").hidden = false;
  } finally {
    $("home-loading").hidden = true;
    $("projects").removeAttribute("aria-busy");
  }
}

function openProject(item) {
  location.href = `/project/${item.id}`;
}

// `prepare` fills the form before it opens; `done` receives the submit result.
function dialog(id, { openers, form, submit, prepare = async () => {}, done = openProject }) {
  const element = $(id),
    action = element.querySelector('[type="submit"]'),
    error = element.querySelector(".form-error");
  const show = (message) => {
    error.textContent = message;
    error.hidden = !message;
  };
  dialogBehavior(element);
  for (const opener of openers)
    $(opener).addEventListener("click", async () => {
      show("");
      action.disabled = false;
      await prepare().catch((reason) => show(reason.message));
      element.showModal();
      element.querySelector("input:not([type=radio])").select();
    });
  for (const close of element.querySelectorAll("[data-close]"))
    close.addEventListener("click", () => element.close());
  $(form).addEventListener("submit", async (event) => {
    event.preventDefault();
    action.disabled = true;
    show("");
    try {
      done(await submit(new FormData($(form))), element);
    } catch (reason) {
      show(reason.message);
      action.disabled = false;
    }
  });
}

async function loadSettings() {
  const settings = await api("/api/settings"),
    note = SOURCE_NOTES[settings.source];
  $("settings-home").value = settings.home;
  $("settings-source").textContent = note ?? "";
  $("settings-source").hidden = !note;
  $("settings-file").textContent = `Saved in ${settings.file}`;
}

dialog("create-dialog", {
  openers: ["open-create", "empty-create"],
  form: "create-form",
  submit: (fields) =>
    api("/api/projects", { name: fields.get("name"), platform: fields.get("platform") }),
});
dialog("settings-dialog", {
  openers: ["open-settings"],
  form: "settings-form",
  prepare: loadSettings,
  submit: (fields) => api("/api/settings", { home: fields.get("home") }, { method: "PUT" }),
  done: (_, element) => {
    element.close();
    refresh();
  },
});
$("open-import").addEventListener("click", () => $("import-file").click());
$("import-file").addEventListener("change", (event) => {
  importArchive(event.target.files[0]);
  event.target.value = "";
});
dropZone();
$("project-search").addEventListener("input", render);
$("retry-projects").addEventListener("click", refresh);
$("clear-search").addEventListener("click", () => {
  $("project-search").value = "";
  render();
  ($("project-search").hidden ? $("open-create") : $("project-search")).focus();
});
// Returning with the browser back button shows current names and thumbnails.
addEventListener("pageshow", (event) => {
  if (event.persisted) refresh();
});
refresh();
