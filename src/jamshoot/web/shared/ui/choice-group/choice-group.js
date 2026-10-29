import { $ } from "../../lib/dom.js";
import { title } from "../../lib/text.js";

// `group` is a fieldset or its id; its id names the radio group.
function sameChoices(inputs, values) {
  return (
    inputs.length === values.length && inputs.every((input, index) => input.value === values[index])
  );
}

export function choices(group, values, selected, onChange, label = title) {
  if (typeof group === "string") group = $(group);
  const existing = [...group.querySelectorAll('input[type="radio"]')];
  if (sameChoices(existing, values)) {
    for (const input of existing) {
      input.checked = input.value === selected;
      input.onchange = () => onChange(input.value);
      input.nextElementSibling.lastChild.textContent = label(input.value);
    }
    return;
  }
  renderChoices(group, values, selected, onChange, label);
}

function renderChoices(group, values, selected, onChange, label) {
  const id = group.id;
  const legend = group.querySelector("legend"),
    track = document.createElement("div");
  track.className = "choice-options";
  track.append(
    ...values.map((value) => {
      const wrapper = document.createElement("label");
      wrapper.className = `choice choice-${value}`;
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = id;
      radio.value = value;
      radio.checked = value === selected;
      radio.onchange = () => onChange(value);
      const text = document.createElement("span");
      text.textContent = label(value);
      wrapper.append(radio, text);
      return wrapper;
    }),
  );
  group.replaceChildren(...(legend ? [legend] : []), track);
}
