// Bounded draft history. No DOM, persistence or project transformations.
const VERBS = { undo: "Undo", redo: "Redo" };

export class DraftHistory {
  constructor(project, selection, limit = 50) {
    this.current = this.snapshot(project, selection, "");
    this.past = [];
    this.future = [];
    this.limit = limit;
    this.group = null;
  }
  snapshot(project, selection, label) {
    return { project: JSON.stringify(project), selection: structuredClone(selection), label };
  }
  select(selection) {
    this.current.selection = structuredClone(selection);
  }
  beginGroup(label) {
    this.endGroup();
    this.group = { label, recorded: false, future: this.future };
  }
  endGroup() {
    if (this.group?.recorded && this.past.at(-1)?.project === this.current.project) {
      this.current = this.past.pop();
      this.future = this.group.future;
    }
    if (this.past.length > this.limit) this.past.shift();
    this.group = null;
  }
  record(project, selection, label = "Edit project") {
    const next = this.snapshot(project, selection, this.group?.label || label);
    if (next.project === this.current.project) return false;
    if (!this.group?.recorded) {
      this.past.push(this.current);
      if (!this.group && this.past.length > this.limit) this.past.shift();
    }
    if (this.group) this.group.recorded = true;
    this.current = next;
    this.future = [];
    return true;
  }
  get canUndo() {
    return this.past.length > 0;
  }
  get canRedo() {
    return this.future.length > 0;
  }
  get undoLabel() {
    return this.canUndo ? this.current.label : "";
  }
  get redoLabel() {
    return this.future.at(-1)?.label || "";
  }
  restore(snapshot) {
    return {
      project: JSON.parse(snapshot.project),
      selection: structuredClone(snapshot.selection),
    };
  }
  // Undo or Redo button state, titled with the step it would restore.
  control(direction) {
    const undo = direction === "undo";
    const enabled = undo ? this.canUndo : this.canRedo;
    const label = undo ? this.undoLabel : this.redoLabel;
    return {
      enabled,
      title: enabled ? `${VERBS[direction]}: ${label}` : `Nothing to ${direction}`,
    };
  }
  // One step back ("undo") or forward ("redo") with its label, or null at either end.
  step(direction) {
    const undo = direction === "undo";
    const label = undo ? this.undoLabel : this.redoLabel;
    const snapshot = undo ? this.undo() : this.redo();
    return snapshot && { ...snapshot, label };
  }
  undo() {
    this.endGroup();
    if (!this.canUndo) return null;
    this.future.push(this.current);
    this.current = this.past.pop();
    return this.restore(this.current);
  }
  redo() {
    this.endGroup();
    if (!this.canRedo) return null;
    this.past.push(this.current);
    this.current = this.future.pop();
    return this.restore(this.current);
  }
}
