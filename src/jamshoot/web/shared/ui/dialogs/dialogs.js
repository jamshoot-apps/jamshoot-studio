import { $ } from "../../lib/dom.js";

export function containTab(event, container) {
  if (event.key !== "Tab") return;
  const elements = [
    ...container.querySelectorAll('button,input,select,textarea,summary,a[href],[tabindex="0"]'),
  ].filter(
    (node) =>
      !node.matches(":disabled") && node.getClientRects().length && !node.closest("[hidden]"),
  );
  const first = elements[0],
    last = elements.at(-1);
  const [boundary, destination] = event.shiftKey ? [first, last] : [last, first];
  focusBoundary(event, boundary, destination);
}

function focusBoundary(event, boundary, destination) {
  if (boundary && document.activeElement === boundary) {
    event.preventDefault();
    destination.focus();
  }
}

export function dialogBehavior(dialog, close = () => dialog.close()) {
  dialog.addEventListener("keydown", (event) => {
    containTab(event, dialog);
    event.stopPropagation();
  });
  dialog.addEventListener("click", (event) => {
    if (event.target !== dialog) return;
    const rect = dialog.getBoundingClientRect();
    if (outside(rect, event.clientX, event.clientY)) close();
  });
}

function outside(rect, x, y) {
  return [
    [x, rect.left, rect.right],
    [y, rect.top, rect.bottom],
  ].some(([point, low, high]) => point < low || point > high);
}

const TAB_KEYS = { ArrowLeft: -1, ArrowRight: 1, Home: -Infinity, End: Infinity };

// A tablist that shows one panel per tab; arrow keys, Home and End move between tabs.
export function tabList(list, onSelect = () => {}) {
  const tabs = [...list.querySelectorAll('[role="tab"]')];
  function select(tab) {
    for (const item of tabs) {
      const selected = item === tab;
      item.setAttribute("aria-selected", String(selected));
      item.tabIndex = selected ? 0 : -1;
      $(item.getAttribute("aria-controls")).hidden = !selected;
    }
    onSelect(tab);
  }
  list.addEventListener("click", (event) => {
    const tab = event.target.closest('[role="tab"]');
    if (tab) select(tab);
  });
  list.addEventListener("keydown", (event) => {
    const index = tabs.indexOf(event.target),
      move = TAB_KEYS[event.key];
    if (index < 0 || move === undefined) return;
    event.preventDefault();
    const next = tabs[Math.max(0, Math.min(tabs.length - 1, index + move))];
    select(next);
    next.focus();
  });
  select(tabs[0]);
}
