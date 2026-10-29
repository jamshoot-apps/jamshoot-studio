// Color math and the per-browser list of recent colors; no DOM.
export const clamp = (value, min, max) => Math.max(min, Math.min(max, value));

export function hexToHSV(hex) {
  const [r, g, b] = hex
    .slice(1)
    .match(/../g)
    .map((value) => parseInt(value, 16) / 255);
  const max = Math.max(r, g, b),
    min = Math.min(r, g, b),
    delta = max - min;
  let h = 0;
  if (delta)
    h =
      60 *
      (max === r
        ? ((g - b) / delta + 6) % 6
        : max === g
          ? (b - r) / delta + 2
          : (r - g) / delta + 4);
  return { h, s: max ? (delta / max) * 100 : 0, v: max * 100 };
}

export function hsvToHex(h, s, v) {
  const saturation = clamp(s, 0, 100) / 100,
    value = clamp(v, 0, 100) / 100;
  const hue = (((h % 360) + 360) % 360) / 60;
  const c = value * saturation,
    x = c * (1 - Math.abs((hue % 2) - 1)),
    m = value - c;
  const rgb = [
    [c, x, 0],
    [x, c, 0],
    [0, c, x],
    [0, x, c],
    [x, 0, c],
    [c, 0, x],
  ][Math.floor(hue)];
  return (
    "#" +
    rgb
      .map((channel) =>
        Math.round((channel + m) * 255)
          .toString(16)
          .padStart(2, "0"),
      )
      .join("")
  );
}

const RECENT_KEY = "jamshoot.recent-colors",
  RECENT_LIMIT = 12;
// Recent colors are a per-browser convenience; projects never depend on them.
export function recentColors() {
  try {
    const stored = JSON.parse(localStorage.getItem(RECENT_KEY) || "[]");
    return Array.isArray(stored)
      ? stored.filter((color) => /^#[0-9a-f]{6}$/.test(color)).slice(0, RECENT_LIMIT)
      : [];
  } catch {
    return [];
  }
}
export function rememberColor(color) {
  const next = [
    color.toLowerCase(),
    ...recentColors().filter((item) => item !== color.toLowerCase()),
  ].slice(0, RECENT_LIMIT);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    /* storage unavailable */
  }
  return next;
}

// The color halfway from `start` to `end` hex colors, at `share` (0–1) of the way.
function mixColors(start, end, share) {
  const channel = (hex, index) => Number.parseInt(hex.slice(1 + index * 2, 3 + index * 2), 16);
  const levels = [0, 1, 2].map((index) =>
    Math.round(channel(start, index) + (channel(end, index) - channel(start, index)) * share),
  );
  return `#${levels.map((level) => level.toString(16).padStart(2, "0")).join("")}`;
}

// The gradient's stops in position order. Without stops it runs from top to bottom; an
// uneven midpoint from older projects becomes an evenly mixed stop at that position.
export function gradientStops(colors, gradient) {
  if (gradient.stops) return [...gradient.stops].sort((a, b) => a.position - b.position);
  const ends = [
    { color: colors.top, position: 0 },
    { color: colors.bottom, position: 100 },
  ];
  if (gradient.midpoint === undefined || gradient.midpoint === 50) return ends;
  const middle = { color: mixColors(colors.top, colors.bottom, 0.5), position: gradient.midpoint };
  return [ends[0], middle, ends[1]];
}

// The color at `position` (0–100) along position-ordered `stops`, as the renderer blends it.
export function colorAt(stops, position) {
  const after = stops.findIndex((stop) => stop.position >= position);
  if (after === -1) return stops.at(-1).color;
  if (after === 0) return stops[0].color;
  const [low, high] = [stops[after - 1], stops[after]];
  const span = high.position - low.position;
  return mixColors(low.color, high.color, span ? (position - low.position) / span : 1);
}

// "red 0%, blue 100%"; `scale` maps stop positions onto the CSS gradient line.
export function cssStops(stops, scale = 1) {
  return stops.map((stop) => `${stop.color} ${stop.position * scale}%`).join(", ");
}

// The CSS twin of the renderer's background fill, for swatches and previews. `gradient` is
// complete: kind, angle, midpoint, optional stops and, for radial fills, center and radius.
export function cssGradient(colors, gradient) {
  const { kind, angle, midpoint = 50 } = gradient;
  if (kind === "solid") return colors.top;
  const scale = kind === "radial" ? gradient.radius / 100 : 1;
  // Without stops the midpoint is a CSS color hint, which curves like the renderer.
  const line = gradient.stops
    ? cssStops(gradientStops(colors, gradient), scale)
    : `${colors.top} 0%, ${midpoint * scale}%, ${colors.bottom} ${100 * scale}%`;
  if (kind === "radial") {
    const { centerX: x, centerY: y } = gradient;
    return `radial-gradient(circle farthest-corner at ${x}% ${y}%, ${line})`;
  }
  return `linear-gradient(${angle}deg, ${line})`;
}
