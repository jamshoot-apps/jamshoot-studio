import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";
import { RenderMemory, remember } from "../src/jamshoot/web/features/preview/render-memory.js";
import { editorShortcut } from "../src/jamshoot/web/pages/editor/shortcuts.js";
import { createAPI } from "../src/jamshoot/web/shared/api.js";
import { DraftHistory } from "../src/jamshoot/web/shared/model/history.js";
import { EditorState, findTarget } from "../src/jamshoot/web/shared/model/project.js";
import {
  colorAt,
  cssGradient,
  gradientStops,
  hexToHSV,
  hsvToHex,
} from "../src/jamshoot/web/shared/ui/color-picker/color.js";

const json = (path) => JSON.parse(readFileSync(new URL(path, import.meta.url), "utf8"));
const project = json("../projects/demo/project.json");

test("editor shortcuts preserve native text undo, support Mac and Windows redo and save in fields", () => {
  const event = { key: "z", target: { closest: () => null } };
  assert.equal(editorShortcut(event), null);
  assert.equal(editorShortcut({ ...event, metaKey: true }), "undo");
  assert.equal(editorShortcut({ ...event, ctrlKey: true, shiftKey: true }), "redo");
  assert.equal(editorShortcut({ ...event, key: "y", ctrlKey: true }), "redo");
  assert.equal(editorShortcut({ ...event, key: "y", metaKey: true }), null);
  assert.equal(editorShortcut({ ...event, ctrlKey: true, altKey: true }), null);
  const field = { closest: () => ({}) };
  assert.equal(editorShortcut({ ...event, metaKey: true, target: field }), null);
  assert.equal(editorShortcut({ ...event, key: "S", ctrlKey: true, target: field }), "save");
});
const schema = json("../src/jamshoot/data/project.schema.json");
const phone = project.targets[0];
const targets = [
  {
    id: phone,
    platform: "iphone",
    layouts: ["auto", "device", "raw"],
    displayGroups: ["phone"],
    orientation: "portrait",
  },
  {
    id: "mac",
    platform: "mac",
    layouts: ["auto", "window", "raw"],
    displayGroups: [],
    orientation: "landscape",
  },
];
const catalog = {
  targets,
  displayGroups: [{ id: "phone", required: true }],
  customSides: [64, 8192],
  customMaxPixels: 24000000,
  custom: { portrait: { layouts: ["auto", "raw"] }, landscape: { layouts: ["auto", "raw"] } },
};
function model() {
  return new EditorState(project, {
    identifiers: schema.$defs,
    styleDefaults: { layout: "auto" },
    starterPalettes: {
      ocean: { top: "#102f57", bottom: "#103344" },
      midnight: { top: "#090d22", bottom: "#1e204a" },
    },
    defaultPalette: "ocean",
    limits: { slides: 10, locales: 3, variants: 3, colorStyles: 5, layoutStyles: 5 },
    customSides: catalog.customSides,
    customMaxPixels: catalog.customMaxPixels,
    targetOf: (id) => findTarget(catalog, id),
  });
}

test("locale edits copy localized screenshots, preserve own keys and protect the last language", () => {
  const state = model();
  state.slide.assets.iphone = { "en-US": "original.png" };
  state.addLocale("__proto__");
  assert.equal(Object.hasOwn(state.slide.copy, "__proto__"), true);
  assert.equal(state.assetPath("iphone"), "original.png");
  state.setFieldText("headline", "Translated");
  assert.notEqual(state.slide.copy["en-US"].headline, "Translated");
  assert.throws(() => state.addLocale("EN-US"), /already exists/);
  assert.throws(() => state.addLocale("bad/name"));
  assert.throws(() => state.addLocale("CON.txt"), /reserved/);
  assert.throws(() => state.addLocale("fr", "missing"), /copy from/);
  state.removeLocale("__proto__");
  assert.deepEqual(state.project.locales, ["en-US"]);
  state.removeLocale("en-US");
  assert.deepEqual(state.project.locales, ["en-US"]);
  assert.equal(Object.hasOwn(state.slide.assets.iphone, "__proto__"), false);
});

test("variants rename selection, reject duplicate ids and restore the implicit default", () => {
  const state = model();
  state.addVariant("dark");
  state.renameVariant("dark", "night");
  assert.equal(state.selection.variant, "night");
  assert.throws(() => state.addVariant("night"), /already exists/);
  assert.throws(() => state.renameVariant("missing", "new"), /no longer exists/);
  state.removeVariant("night");
  state.removeVariant("default");
  assert.equal(state.project.variants, undefined);
  assert.equal(state.selection.variant, "default");
});

test("slide style overrides reset to inherited values without changing project defaults", () => {
  const state = model();
  state.setStyle("pattern", "grid");
  assert.equal(state.styleOf("slide").pattern, "grid");
  assert.equal(state.inheritedStyle().pattern, "dots");
  state.setStyleOption("gradient", "angle", 90);
  state.setTextStyle("headline", "size", 12);
  assert.equal(state.style.typography.headline.size, 12);
  state.setTextStyle("headline", "size", undefined);
  assert.equal(state.slide.style.typography, undefined);
  state.setTextStyle("headline", "weight", 700);
  state.resetTypography("slide", "headline");
  assert.equal(state.slide.style.typography, undefined);
  state.setTextStyle("subtitle", "size", 5);
  state.resetTypography();
  state.resetBackground();
  assert.equal(state.slide.style.gradient, undefined);
  state.resetStyle();
  assert.equal(state.slide.style, undefined);
  assert.equal(state.styleOf("project").pattern, "dots");
});

test("palette and layout libraries preserve appearance when links are deleted", () => {
  const state = model();
  const id = state.saveSavedStyle("palette", state.nextStyleName("palette"), {
    colors: { top: "#123456" },
  });
  assert.equal(state.paletteValue("slide"), `style:${id}`);
  assert.equal(state.style.colors.top, "#123456");
  state.updateSavedStyle("palette", id, "Brand", { colors: { top: "#abcdef" } });
  const copy = state.duplicateSavedStyle("palette", id);
  assert.notEqual(copy, id);
  assert.equal(state.savedStyleUsage("palette", id).length, 1);
  state.deleteSavedStyle("palette", id);
  assert.equal(state.style.colors.top, "#abcdef");
  assert.equal(state.paletteValue("slide"), "custom");
  state.resetPalette();
  assert.equal(state.paletteValue("slide"), "");
  state.setPalette("slide", `style:${copy}`);
  state.setPalette("slide", "starter:midnight");
  const starter = state.paletteValue("slide");
  const adopted = state.project.colorStyles.find((style) => `style:${style.id}` === starter);
  assert.deepEqual([adopted.name, adopted.colors.top], ["Midnight", "#090d22"]);
  state.setPalette("project", "starter:midnight");
  assert.equal(state.paletteValue("project"), starter);
  state.setPalette("project", "starter:ocean");
  assert.equal(state.paletteValue("project"), "starter:ocean");
  assert.equal(state.project.defaults.colorStyle, undefined);
  state.setPalette("slide", "custom");
  assert.throws(() => state.setPalette("slide", "style:missing"), /no longer exists/);
  const layout = state.addSavedStyle("layout", "Spacing", { layoutSettings: { padding: 10 } });
  state.setLayoutStyle("slide", `style:${layout}`);
  assert.equal(state.layoutValue("slide"), `style:${layout}`);
  state.setLayoutStyle("slide", "builtin");
  assert.equal(state.layoutValue("slide"), "builtin");
  state.resetStyleGroup("layoutSettings");
  assert.equal(state.layoutValue("slide"), "");
});

test("screenshot and device changes keep the last target and reject oversized canvases", () => {
  const state = model();
  state.setAsset("iphone", "one.png");
  assert.equal(state.assetPath("iphone"), "one.png");
  state.addPlatform("mac", catalog);
  state.removeTarget(phone);
  state.removeTarget("mac");
  assert.deepEqual(state.project.targets, ["mac"]);
  state.addCustomSize(1000, 2000);
  assert.equal(state.selection.target, "custom.1000x2000");
  assert.throws(() => state.addCustomSize(8192, 8192), /million pixels/);
  assert.throws(() => state.addCustomSize(1, 1000), /whole pixels/);
  assert.equal(findTarget(catalog, "custom.8192x8192"), undefined);
  assert.equal(findTarget(catalog, "missing"), undefined);
});

test("slide duplication is independent and moving/deleting selects a surviving slide", () => {
  const state = model();
  const initial = state.selection.slide;
  state.setSlideName("Original");
  const duplicate = state.duplicateSlide();
  state.setFieldText("headline", "Copy");
  assert.notEqual(state.project.slides[0].copy["en-US"].headline, "Copy");
  state.moveSlide(-1);
  assert.equal(state.project.slides[0].id, duplicate.id);
  state.removeSlide();
  assert.equal(state.selection.slide, initial);
  const added = state.addSlide();
  assert.deepEqual(added.assets, {});
  assert.equal(added.copy["en-US"].headline, "Your headline");
});

test("grouped undo preserves redo after a drag returns to its start and bounds history", () => {
  const history = new DraftHistory({ value: 0 }, { slide: "a" }, 2);
  assert.equal(history.record({ value: 0 }, {}), false);
  history.record({ value: 1 }, {}, "One");
  history.record({ value: 2 }, {}, "Two");
  history.undo();
  history.beginGroup("Drag");
  history.record({ value: 3 }, {});
  history.record({ value: 1 }, {});
  history.endGroup();
  assert.equal(history.redo().project.value, 2);
  history.beginGroup("More");
  history.record({ value: 3 }, {});
  history.record({ value: 4 }, {});
  history.endGroup();
  assert.equal(history.past.length, 2);
  assert.equal(history.undo().project.value, 2);
  assert.equal(history.redo().project.value, 4);
});

test("render memory reuses the plan of an unchanged project and keeps recent renders", () => {
  const cache = new Map([["a", 1]]);
  remember(cache, "b", 2, 2);
  remember(cache, "a", 3, 2);
  remember(cache, "c", 4, 2);
  assert.deepEqual(
    [...cache],
    [
      ["a", 3],
      ["c", 4],
    ],
  );

  const files = [
    { slide: "one", locale: "en-US", target: "phone", variant: "default" },
    { slide: "two", locale: "en-US", target: "phone", variant: "default" },
  ];
  const memory = new RenderMemory(1);
  const selection = { ...files[1] };
  assert.equal(memory.selected("{}", selection), null);
  memory.setPlan("{}", { files });
  assert.equal(memory.plan("{}").files, files);
  assert.equal(memory.plan('{"changed":true}'), null);
  const known = memory.selected("{}", selection);
  assert.deepEqual(known, { item: files[1], key: JSON.stringify(files[1]), render: undefined });
  assert.equal(memory.selected("{}", { ...selection, slide: "missing" }), null);
  memory.store(known.key, { blob: "two" });
  assert.deepEqual(memory.selected("{}", selection).render, { blob: "two" });
  memory.store("other", { blob: "other" });
  assert.equal(memory.render(known.key), undefined);
  memory.forgetPlan();
  assert.equal(memory.plan("{}"), null);
  memory.setPlan("{}", { files });
  memory.clear();
  assert.equal(memory.plan("{}"), null);
  assert.equal(memory.render("other"), undefined);
});

test("color conversion round trips primary colors and gradient kinds preserve stops", () => {
  for (const color of ["#000000", "#ffffff", "#ff0000", "#00ff00", "#0000ff", "#123456"]) {
    const { h, s, v } = hexToHSV(color);
    assert.equal(hsvToHex(h, s, v), color);
  }
  const colors = { top: "#000000", bottom: "#ffffff" };
  assert.equal(cssGradient(colors, { kind: "solid" }), "#000000");
  assert.match(cssGradient(colors, { kind: "linear", angle: 90 }), /linear-gradient\(90deg/);
  assert.match(
    cssGradient(colors, { kind: "radial", radius: 50, centerX: 20, centerY: 30 }),
    /at 20% 30%/,
  );
  const stops = gradientStops(colors, { midpoint: 25 });
  assert.equal(colorAt(stops, 25), "#808080");
  assert.equal(colorAt(stops, -1), "#000000");
  assert.equal(colorAt(stops, 101), "#ffffff");
  assert.match(cssGradient(colors, { kind: "linear", angle: 0, stops }), /#808080 25%/);
});

test("API sends tokens, JSON and raw data, reports structured validation and transport errors", async () => {
  let request;
  const api = createAPI("session", async (_path, options) => {
    request = options;
    return Response.json({ saved: true });
  });
  assert.deepEqual(await api("/project", { name: "App" }), { saved: true });
  assert.equal(request.headers["X-JamShoot-Token"], "session");
  assert.equal(request.body, '{"name":"App"}');
  await api("/upload", new Uint8Array([1]), { raw: true });
  assert.equal(request.headers["Content-Type"], "application/octet-stream");
  await api("/project", "{}", { serialized: true });
  assert.equal(request.body, "{}");
  await api("/project");
  assert.equal(request.body, undefined);
  const rejected = createAPI("session", async () =>
    Response.json(
      { error: { details: [{ path: "/name", message: "Required" }] } },
      { status: 400 },
    ),
  );
  await assert.rejects(rejected("/project"), /\/name: Required/);
  const crashed = createAPI("session", async () => new Response("broken", { status: 500 }));
  await assert.rejects(crashed("/project"), /could not complete/);
  const offline = createAPI("session", async () => {
    throw new Error("offline");
  });
  await assert.rejects(offline("/project"), /Cannot reach/);
});
