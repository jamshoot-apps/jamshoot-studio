// The slide list. Cards are kept by slide id and updated in place, so an edit or a new
// thumbnail changes only what differs: images are not decoded again and focus stays put.
// `loading` holds the slides whose thumbnail is being rendered; they show a spinner.
export function updateSlideList(
  container,
  slides,
  selection,
  thumbnails,
  onSelect,
  loading = new Set(),
) {
  const cards = new Map([...container.children].map((item) => [cardIn(item).dataset.slide, item]));
  const items = slides.map((slide, index) => {
    const item = cards.get(slide.id) ?? newCard(slide.id);
    updateCard(cardIn(item), slide, index, { selection, thumbnails, loading });
    return item;
  });
  if (!inOrder(container.children, items)) reorder(container, items);
  // Handlers are replaced on each update, so they see the current slides.
  container.onclick = (event) => {
    const id = event.target.closest(".slide-card")?.dataset.slide;
    if (id) onSelect(id);
  };
  container.onkeydown = (event) => moveFocus(event, container, slides, onSelect);
}

const cardIn = (item) => item.firstElementChild;

function newCard(id) {
  const item = document.createElement("li"),
    button = document.createElement("button"),
    thumb = document.createElement("span"),
    caption = document.createElement("span");
  button.className = "slide-card";
  button.dataset.slide = id;
  thumb.className = "slide-thumb";
  caption.className = "slide-caption";
  const number = document.createElement("span");
  number.className = "slide-number";
  caption.append(number, document.createElement("span"));
  button.append(thumb, caption);
  item.append(button);
  return item;
}

function updateCard(button, slide, index, { selection, thumbnails, loading }) {
  const name = slide.name || slide.id;
  button.setAttribute("aria-current", String(slide.id === selection.slide));
  button.setAttribute("aria-label", `Slide ${index + 1}: ${name}`);
  const [thumb, caption] = button.children;
  thumb.classList.toggle("is-loading", loading.has(slide.id));
  setThumbnail(thumb, thumbnails.get(slide.id));
  setText(caption.children[0], String(index + 1).padStart(2, "0"));
  setText(caption.children[1], name);
}

function setText(node, text) {
  if (node.textContent !== text) node.textContent = text;
}

// A changed thumbnail URL reuses the card's image, which keeps showing until the new one loads.
function setThumbnail(thumb, url = "") {
  if (thumb.dataset.src === url) return;
  thumb.dataset.src = url;
  if (url) imageIn(thumb).src = url;
  else thumb.replaceChildren("Preview pending");
}

function imageIn(thumb) {
  const image = thumb.querySelector("img");
  if (image) return image;
  const created = document.createElement("img");
  created.alt = "";
  thumb.replaceChildren(created);
  return created;
}

function inOrder(children, items) {
  return children.length === items.length && items.every((item, index) => children[index] === item);
}

// Moving the focused card would blur it, so focus follows it.
function reorder(container, items) {
  const focused = document.activeElement?.dataset.slide;
  container.replaceChildren(...items);
  if (focused) container.querySelector(`[data-slide="${focused}"]`)?.focus();
}

function moveFocus(event, container, slides, onSelect) {
  const id = event.target.closest(".slide-card")?.dataset.slide,
    index = slides.findIndex((slide) => slide.id === id);
  const delta = { ArrowUp: -1, ArrowDown: 1, Home: -index, End: slides.length - index - 1 }[
    event.key
  ];
  if (index < 0 || delta === undefined) return;
  event.preventDefault();
  const next = slides[Math.max(0, Math.min(slides.length - 1, index + delta))].id;
  onSelect(next);
  container.querySelector(`[data-slide="${next}"]`)?.focus();
}
