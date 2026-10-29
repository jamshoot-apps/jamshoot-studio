// The canvas preview and slide thumbnails, rendered by Python's Pillow renderer.

import { $ } from "../../shared/lib/dom.js";
import { previewIndex, thumbnailJobs } from "../../shared/model/project.js";
import { RenderMemory, remember } from "./render-memory.js";

// One burst of input events renders once; thumbnails wait until edits pause.
const BURST_MS = 60;
const IDLE_MS = 400;
// Rendered images kept by their exact job, so a size or slide seen before shows at once:
// thumbnails, and full previews with their guides.
const CACHED_THUMBNAILS = 120;
const CACHED_RENDERS = 30;

function previewError(message) {
  $("preview-error").textContent = message;
  $("preview-error").hidden = !message;
  $("retry-preview").hidden = !message;
  $("preview").classList.toggle("is-stale", !!message);
}

function showImage(visible) {
  $("preview").hidden = !visible;
  $("empty-preview").hidden = visible;
}

// Where the text and screenshot landed in the shown image, or null; see render_job's guides.
function guidesOf(headers) {
  try {
    return JSON.parse(headers?.get("X-JamShoot-Guides") || "null");
  } catch {
    return null;
  }
}

// A preview response as `{ body, headers }`; a plain blob has no headers.
const responseOf = (result) => (result instanceof Blob ? { body: result } : result);

function exportCount(plan, dirty) {
  if (dirty) return "Updating export count…";
  return `${plan.fileCount} PNG ${plan.fileCount === 1 ? "file" : "files"} in export`;
}

export class Preview {
  thumbnails = new Map();
  guides = null;
  // Slides whose thumbnail is being rendered for the current draft and selection.
  loading = new Set();
  pending = false;
  #keys = new Map();
  #cache = new Map();
  #memory = new RenderMemory(CACHED_RENDERS);
  #navigated = false;
  #generation = 0;
  #timer = 0;
  #controller = null;
  // The object URL the canvas owns, and the blob it shows.
  #url = "";
  #shown = null;
  // The canvas already shows the selected slide (a cached render or its thumbnail), so a
  // change of slide needs no "previous version" notice.
  #selected = false;
  #rendering = false;
  #waiting = false;
  #dirty = false;
  #quiet = true;
  #selection = "";

  // `editor.state` is the draft. `onThumbnail()` redraws the slide list, `describe(item)`
  // is the status line for a rendered plan entry and `onGuides()` follows a new image.
  constructor(editor, { api, status, onThumbnail, describe, onGuides = () => {} }) {
    Object.assign(this, { editor, api, status, onThumbnail, describe, onGuides });
  }

  // Canceling starts a new generation, so a stale render never touches the page.
  cancel() {
    this.#generation++;
    this.loading.clear();
    this.#rendering = this.#waiting = false;
    clearTimeout(this.#timer);
    this.#controller?.abort();
  }

  // Neither a running render nor a waiting one is restarted: the next render follows with
  // the latest draft, so the preview keeps moving while a slider is dragged. `navigated`
  // marks a change of slide, language, variant or size, whose thumbnails need not wait
  // for typing to pause.
  schedule(quiet = false, { navigated = false } = {}) {
    const { state } = this.editor;
    const changedSelection = this.#select(state);
    this.pending = this.#dirty = true;
    previewError("");
    this.#markPending();
    $("file-count").textContent = "Updating export count…";
    this.#quiet &&= quiet;
    this.#navigated ||= navigated || changedSelection;
    this.#queue();
  }

  #select(state) {
    const selection = JSON.stringify(state.selection);
    if (selection === this.#selection) return false;
    const navigated = Boolean(this.#selection);
    this.#selection = selection;
    this.cancel();
    $("preview-title").textContent = `${state.slideName} · ${state.selection.locale}`;
    $("dimensions").textContent = "—";
    this.#selected = this.#showKnown(state);
    if (!this.#selected) {
      showImage(false);
      $("empty-preview").querySelector("p").textContent = "Preparing preview…";
    }
    return navigated;
  }

  // Shows the selected slide without a request when the draft's plan is known: its full
  // render if cached, else its current thumbnail until the render lands.
  #showKnown(state) {
    const known = this.#memory.selected(JSON.stringify(state.project), state.selection);
    if (!known) return false;
    return known.render ? this.#showRendered(known) : this.#showThumbnail(known);
  }

  #showRendered({ item, render }) {
    this.#showBlob(render.blob);
    $("dimensions").textContent = `${item.width} × ${item.height} px`;
    return true;
  }

  // Only a thumbnail of this exact plan entry stands in for its render.
  #showThumbnail({ item, key }) {
    if (this.#keys.get(item.slide) !== key) return false;
    this.#setSource(this.thumbnails.get(item.slide));
    return true;
  }

  #showBlob(blob) {
    if (blob !== this.#shown) this.#setSource(URL.createObjectURL(blob), blob);
  }

  // Shows `src`; the canvas owns it, and revokes it later, only when it was made for `blob`.
  #setSource(src, blob = null) {
    if (this.#url) URL.revokeObjectURL(this.#url);
    this.#url = blob ? src : "";
    this.#shown = blob;
    $("preview").src = src;
    showImage(true);
  }

  #queue() {
    if (this.#rendering || this.#waiting) return;
    this.cancel();
    this.#waiting = true;
    this.#timer = setTimeout(() => {
      this.#waiting = false;
      this.#update();
    }, BURST_MS);
  }

  // The notice only explains an image of the previous draft or slide; the empty state
  // already says a first preview is coming.
  #markPending() {
    $("preview-updating").hidden = !this.pending || $("preview").hidden || this.#selected;
    $("preview").setAttribute("aria-busy", String(this.pending));
    if (this.pending) {
      this.guides = null;
      this.onGuides();
    }
  }

  // Frees thumbnails of slides that are not kept; with no slides given, frees all of them.
  // Dropping them all, as a project loads from disk, also forgets the caches: files the
  // jobs name may have changed.
  dropThumbnails(keep = new Set()) {
    if (!keep.size) {
      this.#cache.clear();
      this.#memory.clear();
    }
    for (const [slide, url] of this.thumbnails) {
      if (keep.has(slide)) continue;
      URL.revokeObjectURL(url);
      this.thumbnails.delete(slide);
      this.#keys.delete(slide);
    }
  }

  forgetPlan() {
    this.#memory.forgetPlan();
  }

  #isCurrent(job) {
    return job.generation === this.#generation;
  }

  #setThumbnail(slide, key, blob) {
    this.loading.delete(slide);
    remember(this.#cache, key, blob, CACHED_THUMBNAILS);
    if (this.#keys.get(slide) === key) return;
    if (this.thumbnails.has(slide)) URL.revokeObjectURL(this.thumbnails.get(slide));
    this.thumbnails.set(slide, URL.createObjectURL(blob));
    this.#keys.set(slide, key);
  }

  #show(plan, item, key, render) {
    this.#showBlob(render.blob);
    this.#selected = false;
    previewError("");
    $("preview-title").textContent = `${this.editor.state.slideName} · ${item.locale}`;
    $("dimensions").textContent = `${item.width} × ${item.height} px`;
    $("file-count").textContent = exportCount(plan, this.#dirty);
    this.#setThumbnail(item.slide, key, render.blob);
    this.pending = this.#dirty;
    this.guides = this.pending ? null : render.guides;
    this.onGuides();
    this.onThumbnail();
    this.#markPending();
  }

  // A failed render keeps the last good preview visible, dimmed, with the reason on top.
  #failed(job, error) {
    if (!this.#isCurrent(job)) return;
    this.pending = this.#dirty;
    this.#markPending();
    this.status(error.message, true);
    previewError(`Preview not updated: ${error.message}`);
    if (!this.#url) showImage(false);
    $("empty-preview").hidden = true;
  }

  // Cached thumbnails show at once and the rest are marked loading; returns those to render.
  #thumbnailQueue(job, plan) {
    const queue = [];
    for (const entry of thumbnailJobs(plan.files, job.selection, this.#keys)) {
      const cached = this.#cache.get(entry.key);
      if (cached) this.#setThumbnail(entry.slide, entry.key, cached);
      else {
        this.loading.add(entry.slide);
        queue.push(entry);
      }
    }
    this.onThumbnail();
    return queue;
  }

  // One at a time; a failed thumbnail keeps its previous image, the main preview reports errors.
  async #renderThumbnails(job, queue) {
    for (const { index, slide, key } of queue) {
      const body = { project: job.project, index, thumbnail: true };
      const blob = await this.api("/preview", body, job.options).catch(() => null);
      if (!this.#isCurrent(job)) return;
      if (blob) this.#setThumbnail(slide, key, blob);
      else this.loading.delete(slide);
      this.onThumbnail();
    }
  }

  // The plan depends only on the project, so a change of slide or size reuses it.
  async #planOf(job) {
    const project = JSON.stringify(job.project);
    const known = this.#memory.plan(project);
    if (known) return known;
    const plan = await this.api("/plan", { project: job.project }, job.options);
    this.#memory.setPlan(project, plan);
    return plan;
  }

  // The full preview of plan entry `index`, remembered or rendered; null once the job is stale.
  #renderOf(job, index, key) {
    return this.#memory.render(key) ?? this.#fetchRender(job, index);
  }

  async #fetchRender(job, index) {
    const options = { ...job.options, withHeaders: true };
    const result = await this.api("/preview", { project: job.project, index }, options);
    if (!this.#isCurrent(job)) return null;
    const { body, headers } = responseOf(result);
    return { blob: body, guides: guidesOf(headers) };
  }

  async #render(job, quiet) {
    const plan = await this.#planOf(job);
    if (!this.#isCurrent(job)) return null;
    const index = previewIndex(plan.files, job.selection),
      item = plan.files[index],
      key = JSON.stringify(item);
    const render = await this.#renderOf(job, index, key);
    if (!render) return null;
    this.#memory.store(key, render);
    this.#show(plan, item, key, render);
    if (!quiet) this.status(this.describe(item));
    return plan;
  }

  #job() {
    this.#controller = new AbortController();
    const { state } = this.editor;
    return {
      generation: this.#generation,
      project: structuredClone(state.project),
      selection: { ...state.selection },
      options: { signal: this.#controller.signal },
    };
  }

  async #update() {
    const quiet = this.#quiet;
    this.#dirty = false;
    this.#quiet = true;
    this.#rendering = true;
    const job = this.#job();
    if (!quiet) this.status("Rendering preview…");
    $("workspace").classList.add("is-rendering");
    const plan = await this.#render(job, quiet).catch((error) => this.#failed(job, error));
    if (this.#isCurrent(job)) this.#finish(job, plan);
  }

  // Edits made during the render start the next one at once; thumbnails wait for a pause.
  #finish(job, plan) {
    this.#rendering = false;
    if (this.#dirty) {
      this.#update();
      return;
    }
    $("workspace").classList.remove("is-rendering");
    if (!plan) return;
    const delay = this.#navigated ? 0 : IDLE_MS;
    this.#navigated = false;
    this.#timer = setTimeout(
      () => this.#renderThumbnails(job, this.#thumbnailQueue(job, plan)),
      delay,
    );
  }
}
