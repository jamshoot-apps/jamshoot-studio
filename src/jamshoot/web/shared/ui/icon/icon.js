export function icon(name) {
  const element = document.createElement("span");
  element.className = `icon icon-${name}`;
  element.setAttribute("aria-hidden", "true");
  return element;
}
