// Spacing guides over the canvas, like a design tool's: while a spacing or text setting is
// hovered, focused or dragged in the slide panel, the image shows the text boxes, the
// columns and the screenshot, and measures the setting being changed in pixels.

const SVG = "http://www.w3.org/2000/svg";
// Label text size and padding in screen pixels, scaled into canvas pixels when drawn.
const LABEL_PX = 11;
const LABEL_PAD = 4;

const first = (guides) => Object.values(guides.copy)[0];
const last = (guides) => Object.values(guides.copy).at(-1);
const middle = ([left, , right]) => (left + right) / 2;

// A measure: from (x1, y1) to (x2, y2) in canvas pixels, or null when it does not apply.
const vertical = (x, top, bottom) => (bottom > top ? [x, top, x, bottom] : null);
const horizontal = (y, left, right) => (right > left ? [left, y, right, y] : null);

function between(guides, upper, lower) {
  const [a, b] = [guides.copy[upper], guides.copy[lower]];
  return a && b ? vertical(middle(b), a[3], b[1]) : null;
}

const MEASURES = {
  topMargin: (g) => vertical(middle(first(g)), 0, first(g)[1]),
  labelGap: (g) => between(g, "featureLabel", "headline"),
  subtitleGap: (g) => between(g, "headline", "subtitle"),
  screenshotGap: (g) => vertical(middle(g.frame), last(g)[3], g.frame[1]),
  screenshotTop: (g) => vertical(g.frame[0], 0, g.frame[1]),
  bottomMargin: (g) => vertical(middle(g.frame), g.frame[3], g.canvas[1]),
  textWidth: (g) => horizontal(first(g)[1] - LABEL_PX * 2, g.text[0], g.text[1]),
  screenshotWidth: (g) => horizontal((g.frame[1] + g.frame[3]) / 2, g.screen[0], g.screen[1]),
};

function element(name, attributes) {
  const node = document.createElementNS(SVG, name);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  return node;
}

const rect = ([left, top, right, bottom], className) =>
  element("rect", {
    x: left,
    y: top,
    width: right - left,
    height: bottom - top,
    class: className,
  });

const line = ([x1, y1, x2, y2], className) => element("line", { x1, y1, x2, y2, class: className });

// A pill with `text` centered on (x, y); `scale` is canvas pixels per screen pixel.
function label(text, x, y, scale) {
  const size = LABEL_PX * scale,
    pad = LABEL_PAD * scale;
  const width = text.length * size * 0.62 + pad * 2,
    height = size + pad * 2;
  const group = element("g", { class: "guide-label" });
  group.append(
    element("rect", { x: x - width / 2, y: y - height / 2, width, height, rx: height / 2 }),
    Object.assign(
      element("text", { x, y, "font-size": size, "text-anchor": "middle", dy: "0.35em" }),
      { textContent: text },
    ),
  );
  return group;
}

// The measure line with end ticks and its length.
function measure(points, scale) {
  const [x1, y1, x2, y2] = points;
  const tick = 6 * scale;
  const across = y1 === y2;
  const ticks = [
    [x1, y1],
    [x2, y2],
  ].map(([x, y]) =>
    line(across ? [x, y - tick, x, y + tick] : [x - tick, y, x + tick, y], "guide-measure"),
  );
  const length = Math.hypot(x2 - x1, y2 - y1);
  // A short measure keeps its line visible: the label moves beside it.
  const aside = length / scale < LABEL_PX * 4 ? (LABEL_PX * 2 + LABEL_PAD * 2) * scale : 0;
  const x = (x1 + x2) / 2 + (across ? 0 : aside),
    y = (y1 + y2) / 2 + (across ? aside : 0);
  return [line(points, "guide-measure"), ...ticks, label(`${Math.round(length)}`, x, y, scale)];
}

// Whether guides apply: the renderer reported them, a setting is active and the image shows.
const applies = ({ guides, active, image }) =>
  Boolean(guides?.copy && active && visibleImage(image));

const visibleImage = (image) => !image.hidden && image.offsetWidth;

// A text field's box and font size, or nothing when the field is empty.
function fieldHighlight(guides, field, scale) {
  const box = guides.copy[field];
  if (!box) return [];
  const text = `${guides.sizes[field]} px`;
  return [rect(box, "guide-active"), label(text, middle(box), box[1] - 12 * scale, scale)];
}

export class GuideOverlay {
  guides = null;
  active = null;

  // `image` is the preview <img>; the overlay sits exactly over it.
  constructor(image) {
    this.image = image;
    this.svg = element("svg", { class: "guide-overlay", "aria-hidden": "true" });
    this.svg.hidden = true;
    image.after(this.svg);
    new ResizeObserver(() => this.#draw()).observe(image);
  }

  // Guides of the image now shown, from the renderer; null hides them.
  setGuides(guides) {
    this.guides = guides;
    this.#draw();
  }

  // The setting being changed: a spacing key such as "topMargin", "text:headline" for a
  // text field's text settings, or null when nothing is.
  setActive(active) {
    if (active === this.active) return;
    this.active = active;
    this.#draw();
  }

  #draw() {
    const { guides, image, svg } = this;
    svg.hidden = !applies(this);
    if (svg.hidden) return;
    const [width, height] = guides.canvas;
    Object.assign(svg.style, {
      left: `${image.offsetLeft}px`,
      top: `${image.offsetTop}px`,
      width: `${image.offsetWidth}px`,
      height: `${image.offsetHeight}px`,
    });
    svg.setAttribute("viewBox", `0 0 ${width} ${height}`);
    const scale = width / image.offsetWidth;
    svg.replaceChildren(...this.#outlines(), ...this.#highlight(scale));
  }

  // Every constraint, faintly: the text boxes, both columns and the screenshot.
  #outlines() {
    const { guides } = this;
    const [, height] = guides.canvas;
    return [
      ...Object.values(guides.copy).map((box) => rect(box, "guide-box")),
      ...[...guides.text, ...guides.screen].map((x) => line([x, 0, x, height], "guide-column")),
      rect(guides.frame, "guide-box"),
    ];
  }

  // The active setting: a text field's box and font size, or a measured distance.
  #highlight(scale) {
    const { guides, active } = this;
    if (active.startsWith("text:")) return fieldHighlight(guides, active.slice(5), scale);
    const points = MEASURES[active]?.(guides);
    return points ? measure(points, scale) : [];
  }
}

// The setting a control in the slide panel changes, from its number field's id: spacing
// ("layout-topMargin") or a text setting of `field` ("type-size").
export function guideKey(id, field) {
  if (id.startsWith("layout-")) return id.slice(7);
  if (id.startsWith("type-")) return `text:${field}`;
  return null;
}
