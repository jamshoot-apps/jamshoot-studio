// What the canvas has rendered: the last plan and full previews, so a slide seen before
// shows without a request. Previews are kept by their exact plan entry.

import { planEntry } from "../../shared/model/project.js";

// Stores `value` as the most recent entry, dropping the oldest beyond `limit`.
export function remember(cache, key, value, limit) {
  cache.delete(key);
  cache.set(key, value);
  if (cache.size > limit) cache.delete(cache.keys().next().value);
}

export class RenderMemory {
  #plan = null;
  #renders = new Map();

  constructor(limit) {
    this.limit = limit;
  }

  // The plan made for this project JSON, if it is the last one.
  plan(project) {
    return this.#plan?.project === project ? this.#plan.plan : null;
  }

  setPlan(project, plan) {
    this.#plan = { project, plan };
  }

  // The plan names font files found on disk, so new fonts need a new plan.
  forgetPlan() {
    this.#plan = null;
  }

  // `{ blob, guides }` rendered for a plan entry's key.
  render(key) {
    return this.#renders.get(key);
  }

  store(key, render) {
    remember(this.#renders, key, render, this.limit);
  }

  // The selected entry of a known plan with its key and render, or null.
  selected(project, selection) {
    const item = planEntry(this.plan(project)?.files ?? [], selection);
    if (!item) return null;
    const key = JSON.stringify(item);
    return { item, key, render: this.render(key) };
  }

  clear() {
    this.#plan = null;
    this.#renders.clear();
  }
}
