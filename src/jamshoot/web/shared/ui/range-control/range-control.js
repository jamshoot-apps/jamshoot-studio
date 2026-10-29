// A hundredth of the range rounded down to a power of ten: 1° for rotation, 0.01 for stroke.
const sliderStep = ({ minimum, maximum }) =>
  10 ** Math.floor(Math.log10((maximum - minimum) / 100));

// The slider moves in round steps and one drag is one edit session; the number field keeps
// any valid typed precision.
export function rangeControl(container, id, caption, limits, onChange, session = {}) {
  const row = document.createElement("div"),
    label = document.createElement("label");
  const range = document.createElement("input"),
    number = document.createElement("input");
  row.className = "range-control";
  label.htmlFor = id;
  label.textContent = caption;
  range.type = "range";
  range.setAttribute("aria-label", `${caption} slider`);
  number.type = "number";
  number.id = id;
  number.required = true;
  for (const input of [range, number]) {
    input.min = limits.minimum;
    input.max = limits.maximum;
  }
  range.step = String(sliderStep(limits));
  number.step = "any";
  let dragging = false;
  // Computed defaults such as 18.8235294… display rounded; typed precision is kept.
  function update(value) {
    range.value = value;
    number.value = /\.\d{7,}/.test(String(value))
      ? String(Math.round(value * 100) / 100)
      : String(value);
  }
  function change(input) {
    if (!input.checkValidity()) {
      input.reportValidity();
      return;
    }
    const value = input.valueAsNumber;
    update(value);
    onChange(value);
  }
  range.addEventListener("input", () => {
    if (!dragging) session.onStart?.();
    dragging = true;
    change(range);
  });
  // A drag back to its start value fires no change, so release and blur also end it.
  for (const type of ["change", "pointerup", "blur"])
    range.addEventListener(type, () => {
      if (dragging) session.onEnd?.();
      dragging = false;
    });
  number.addEventListener("change", () => change(number));
  row.append(label, range, number);
  container.append(row);
  // A new caption and bounds, such as the same setting shown in pixels.
  function configure({ caption: text, minimum, maximum, step }) {
    label.textContent = text;
    range.setAttribute("aria-label", `${text} slider`);
    for (const input of [range, number]) {
      input.min = minimum;
      input.max = maximum;
    }
    range.step = String(step ?? sliderStep({ minimum, maximum }));
  }
  return { update, configure, element: row };
}

// A slider's history session: one drag is one step named `label`.
export function rangeSession({ onStart, onEnd } = {}, label) {
  return { onStart: () => onStart?.(label), onEnd };
}
