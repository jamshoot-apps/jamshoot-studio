// ⌘/Ctrl+S saves everywhere; text fields keep their native Undo and Redo.
export function editorShortcut(event) {
  if (!(event.metaKey || event.ctrlKey) || event.altKey) return null;
  const key = event.key.toLowerCase();
  if (key === "s") return "save";
  if (event.target.closest?.('input,textarea,[contenteditable="true"]')) return null;
  if ((key === "z" && event.shiftKey) || (key === "y" && event.ctrlKey)) return "redo";
  return key === "z" ? "undo" : null;
}
