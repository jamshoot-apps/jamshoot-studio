import { icon } from "../icon/icon.js";

// One button anatomy for the whole Studio: text, icon + text, or icon-only (labeled).
function buttonClass(variant, size, iconOnly) {
  return ["btn", variant && `btn-${variant}`, size && `btn-${size}`, iconOnly && "btn-icon"]
    .filter(Boolean)
    .join(" ");
}

function buttonLabel(element, label, iconOnly, hint) {
  if (iconOnly) {
    element.setAttribute("aria-label", label);
    element.title = hint || label;
    return;
  }
  element.append(document.createTextNode(label));
  if (hint) element.title = hint;
}

export function button({
  label,
  icon: iconName,
  variant = "",
  size = "",
  iconOnly = false,
  title: hint,
  onClick,
} = {}) {
  const element = document.createElement("button");
  element.type = "button";
  element.className = buttonClass(variant, size, iconOnly);
  if (iconName) element.append(icon(iconName));
  buttonLabel(element, label, iconOnly, hint);
  if (onClick) element.addEventListener("click", onClick);
  return element;
}
