import { $ } from "../../lib/dom.js";
import { title } from "../../lib/text.js";

export function options(id, items, selected, label = title) {
  const select = $(id);
  select.replaceChildren(...items.map((item) => new Option(label(item), item)));
  select.value = selected;
  select.disabled = items.length < 2;
  select.menu?.refresh();
}
