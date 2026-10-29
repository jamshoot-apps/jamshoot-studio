// Draft transformations and plan queries; no DOM or network.

import { title, words } from "../lib/text.js";

// Saved style libraries that defaults, variants and slides link by id. `groups` are the
// value groups an entry holds and a linking scope may override key by key; the first is
// the one every entry has.
export const LIBRARIES = {
  palette: {
    list: "colorStyles",
    link: "colorStyle",
    groups: ["colors", "gradient"],
    noun: "Palette",
    plural: "palettes",
  },
  layout: {
    list: "layoutStyles",
    link: "layoutStyle",
    groups: ["layoutSettings"],
    noun: "Template",
    plural: "layout templates",
  },
};

// The value groups of a saved entry, or of a scope's own style, that `kind` links.
function entryOf(kind, source) {
  return Object.fromEntries(
    LIBRARIES[kind].groups.filter((group) => source[group]).map((group) => [group, source[group]]),
  );
}

function ensure(object, key) {
  object[key] ??= {};
  return object[key];
}

const isEmpty = (object) => !Object.keys(object ?? {}).length;

function styleName(name, noun) {
  const trimmed = name.trim();
  if (!trimmed || trimmed.length > 200)
    throw new Error(`${noun} name must contain 1–200 characters.`);
  return trimmed;
}

// What the editor needs from the snapshot to follow Python's rules.
// Explicit layouts that some chosen size does not allow fall back to automatic.
function autoUnsupportedLayouts(scopes, targets) {
  const allowed = (layout) => targets.every((target) => target.layouts.includes(layout));
  for (const style of scopes) if (style.layout && !allowed(style.layout)) style.layout = "auto";
}

const CUSTOM_TARGET = /^custom\.([1-9]\d*)x([1-9]\d*)$/;

// A catalog size, or a custom one ("custom.1080x1920") with the snapshot's rules for its
// orientation; undefined when unknown.
export function findTarget(catalog, id) {
  const known = catalog.targets.find((target) => target.id === id);
  const match = CUSTOM_TARGET.exec(id);
  if (known || !match) return known;
  const [width, height] = match.slice(1).map(Number);
  const [minimum, maximum] = catalog.customSides;
  if (
    ![width, height].every(
      (side) => Number.isInteger(side) && side >= minimum && side <= maximum,
    ) ||
    width * height > catalog.customMaxPixels
  )
    return undefined;
  const orientation = width > height ? "landscape" : "portrait";
  return {
    ...catalog.custom[orientation],
    id,
    platform: "custom",
    width,
    height,
    orientation,
    displayGroups: [],
  };
}

export function editorRules({ schema, appearance, catalog }) {
  const lists = [
    "slides",
    "locales",
    "variants",
    ...Object.values(LIBRARIES).map((library) => library.list),
  ];
  return {
    limits: Object.fromEntries(lists.map((list) => [list, schema.properties[list].maxItems])),
    styleDefaults: appearance.styleDefaults,
    starterPalettes: appearance.starterPalettes,
    defaultPalette: appearance.defaultPalette,
    identifiers: schema.$defs,
    ...(catalog && {
      targetOf: (id) => findTarget(catalog, id),
      customSides: catalog.customSides,
      customMaxPixels: catalog.customMaxPixels,
    }),
  };
}

// The resolved style's colors over the default palette, as in Python's resolve_colors.
export function paletteOf(appearance, style) {
  return { ...appearance.starterPalettes[appearance.defaultPalette], ...style.colors };
}

// Everything a palette saves from a resolved style: its colors and gradient shape.
export function paletteEntry(appearance, style) {
  const entry = { colors: paletteOf(appearance, style) };
  if (Object.keys(style.gradient || {}).length) entry.gradient = { ...style.gradient };
  return entry;
}

export function resolvedLayout(layout, target) {
  return layout === "auto" ? target.autoLayout : layout;
}

// Built-in spacing of the style's layout on `target`.
export function layoutDefaults(style, target) {
  return target.layoutDefaults[resolvedLayout(style.layout, target)];
}

// Each text field's font, size, weight, line height, letter spacing and case on `target`,
// as in Python's resolve_text.
export function textSettings(style, target) {
  const defaults = target.typographyDefaults[resolvedLayout(style.layout, target)];
  return Object.fromEntries(
    Object.entries(defaults).map(([field, values]) => [
      field,
      { ...values, ...style.typography?.[field] },
    ]),
  );
}

// Layouts every target allows; the current one stays listed so it can be changed.
export function layoutChoices(layouts, current, targets) {
  return layouts.filter(
    (layout) => layout === current || targets.every((target) => target.layouts.includes(layout)),
  );
}

export class EditorState {
  // `limits` maps a project list such as "slides" to its maximum length; `targetOf` resolves
  // a target id to its size and layout rules.
  constructor(project, rules = {}) {
    const { limits = {}, styleDefaults = {}, identifiers = {} } = rules;
    const { starterPalettes = {}, defaultPalette = "" } = rules;
    const {
      targetOf = () => undefined,
      customSides = [1, Infinity],
      customMaxPixels = Infinity,
    } = rules;
    Object.assign(this, {
      limits,
      styleDefaults,
      starterPalettes,
      defaultPalette,
      identifiers,
      targetOf,
      customSides,
      customMaxPixels,
    });
    this.selection = {};
    this.replace(project);
  }

  limitOf(list) {
    return this.limits[list] ?? Infinity;
  }
  isFull(list) {
    return (this.project[list]?.length ?? 0) >= this.limitOf(list);
  }

  replace(project) {
    this.project = structuredClone(project);
    const choices = {
      slide: project.slides.map((item) => item.id),
      locale: project.locales,
      target: project.targets,
      variant: this.variants.map((item) => item.id),
    };
    for (const [key, values] of Object.entries(choices)) {
      if (!values.includes(this.selection[key])) this.selection[key] = values[0];
    }
  }

  select(key, value) {
    this.selection[key] = value;
  }
  get slide() {
    return this.project.slides.find((item) => item.id === this.selection.slide);
  }
  get slideName() {
    return this.slide.name || this.slide.id;
  }
  // A project without variants renders one implicit "default" variant.
  get variants() {
    return this.project.variants || [{ id: "default" }];
  }
  get variant() {
    return this.project.variants?.find((item) => item.id === this.selection.variant);
  }

  #identifier(value, kind) {
    const trimmed = value.trim(),
      rule = this.identifiers[kind];
    if (trimmed.length > rule.maxLength || !new RegExp(rule.pattern).test(trimmed))
      throw new Error(
        {
          locale:
            "A language name can't use / \\ : * ? \" < > | or start or end with a space or dot (64 characters max).",
          id: "Use an id starting with a lowercase letter, followed by lowercase letters, digits or hyphens (64 characters max).",
        }[kind],
      );
    const basename = trimmed.split(".", 1)[0].replace(/ +$/, "");
    if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i.test(basename))
      throw new Error("That name is reserved on Windows.");
    return trimmed;
  }
  #checkCapacity(list) {
    if (this.isFull(list))
      throw new Error(`Project supports at most ${this.limitOf(list)} ${list}.`);
  }
  addLocale(value, source = this.selection.locale) {
    const locale = this.#identifier(value, "locale");
    if (this.project.locales.some((item) => item.toLowerCase() === locale.toLowerCase()))
      throw new Error("That language already exists.");
    if (!this.project.locales.includes(source)) throw new Error("Choose a language to copy from.");
    this.#checkCapacity("locales");
    for (const slide of this.project.slides) {
      slide.copy = { ...slide.copy, [locale]: structuredClone(slide.copy[source]) };
      for (const [platform, asset] of Object.entries(slide.assets))
        if (typeof asset === "object" && Object.hasOwn(asset, source) && asset[source])
          slide.assets[platform] = { ...asset, [locale]: asset[source] };
    }
    this.project.locales.push(locale);
    this.selection.locale = locale;
  }
  removeLocale(locale) {
    if (this.project.locales.length <= 1 || !this.project.locales.includes(locale)) return;
    this.project.locales = this.project.locales.filter((item) => item !== locale);
    for (const slide of this.project.slides) {
      delete slide.copy[locale];
      for (const [platform, asset] of Object.entries(slide.assets)) {
        if (typeof asset !== "object") continue;
        delete asset[locale];
        if (!Object.keys(asset).length) delete slide.assets[platform];
      }
    }
    if (this.selection.locale === locale) this.selection.locale = this.project.locales[0];
  }
  #variantId(value, previous) {
    const id = this.#identifier(value, "id");
    if (id !== previous && this.variants.some((item) => item.id === id))
      throw new Error("That variant id already exists.");
    return id;
  }
  addVariant(value) {
    const id = this.#variantId(value);
    if (this.variants.length >= this.limitOf("variants"))
      throw new Error(`Project supports at most ${this.limitOf("variants")} variants.`);
    this.project.variants = [...this.variants, { id }];
    this.selection.variant = id;
  }
  renameVariant(previous, value) {
    const variant = this.variants.find((item) => item.id === previous);
    if (!variant) throw new Error("Variant no longer exists.");
    const id = this.#variantId(value, previous);
    this.project.variants ??= [variant];
    variant.id = id;
    if (this.selection.variant === previous) this.selection.variant = id;
  }
  removeVariant(id) {
    if (!this.project.variants?.some((item) => item.id === id)) return;
    this.project.variants = this.project.variants.filter((item) => item.id !== id);
    if (!this.project.variants.length) delete this.project.variants;
    if (this.selection.variant === id) this.selection.variant = this.variants[0].id;
  }

  #layers(slide, variant = {}) {
    const { id, ...overrides } = variant;
    return [this.project.defaults, overrides, slide.style || {}];
  }
  // Every scope that can hold style values or links.
  #styleScopes() {
    return [
      this.project.defaults,
      ...(this.project.variants || []),
      ...this.project.slides.map((slide) => slide.style || {}),
    ];
  }
  resolveStyle(layers) {
    const style = Object.assign({}, this.styleDefaults, ...layers);
    style.patternSettings = Object.assign({}, ...layers.map((layer) => layer.patternSettings));
    // Typography merges per text field, then setting by setting.
    style.typography = {};
    for (const layer of layers)
      for (const [field, values] of Object.entries(layer.typography || {}))
        style.typography[field] = { ...style.typography[field], ...values };
    // Like Python's effective_style: a link restarts each group from the saved entry.
    for (const { list, link, groups } of Object.values(LIBRARIES))
      for (const group of groups) {
        style[group] = {};
        for (const layer of layers) {
          if (Object.hasOwn(layer, link)) {
            const saved = this.project[list]?.find((item) => item.id === layer[link]);
            style[group] = { ...saved?.[group] };
          }
          Object.assign(style[group], layer[group]);
        }
      }
    return style;
  }
  get defaultStyle() {
    return this.resolveStyle([this.project.defaults]);
  }
  // What the selected slide would look like without its own overrides.
  inheritedStyle() {
    return this.resolveStyle(this.#layers({}, this.variant));
  }
  get style() {
    return this.resolveStyle(this.#layers(this.slide, this.variant));
  }
  styleOf(scope) {
    return scope === "project" ? this.defaultStyle : this.style;
  }
  // The scope's own values: the project defaults, or the slide's overrides.
  ownStyle(scope) {
    return scope === "project" ? this.project.defaults : this.slide.style || {};
  }
  writableStyle(scope) {
    return scope === "project" ? this.project.defaults : ensure(this.slide, "style");
  }
  #dropEmptySlideStyle(scope) {
    if (scope === "slide" && !Object.keys(this.slide.style || {}).length) delete this.slide.style;
  }

  setFieldText(key, value) {
    this.slide.copy[this.selection.locale][key] = value;
  }
  setSlideName(value) {
    const name = value.trim();
    if (name.length > 200) throw new Error("Slide name must be at most 200 characters.");
    if (name) this.slide.name = name;
    else delete this.slide.name;
  }
  setStyle(key, value, scope = "slide") {
    this.writableStyle(scope)[key] = value;
  }
  resetStyle() {
    delete this.slide.style;
  }
  setStyleOption(group, key, value, scope = "slide") {
    ensure(this.writableStyle(scope), group)[key] = value;
  }
  // One text setting of a text field; `undefined` removes it, and empty groups go with it.
  setTextStyle(field, key, value, scope = "slide") {
    if (value !== undefined) {
      ensure(ensure(this.writableStyle(scope), "typography"), field)[key] = value;
      return;
    }
    const typography = this.ownStyle(scope).typography;
    if (!typography?.[field]) return;
    delete typography[field][key];
    this.#dropEmptyTypography(scope, field);
  }
  // Drops a field's own text settings, or every field's without `field`.
  resetTypography(scope = "slide", field = null) {
    const own = this.ownStyle(scope);
    if (!own.typography) return;
    if (field) delete own.typography[field];
    else delete own.typography;
    this.#dropEmptyTypography(scope, field);
  }
  #dropEmptyTypography(scope, field) {
    const own = this.ownStyle(scope);
    const typography = own.typography ?? {};
    if (isEmpty(typography[field])) delete typography[field];
    if (isEmpty(typography)) delete own.typography;
    this.#dropEmptySlideStyle(scope);
  }
  // Without any of a library's groups left, an unlinked scope inherits the link again.
  resetStyleGroup(group, scope = "slide") {
    const own = this.ownStyle(scope);
    delete own[group];
    for (const { link, groups } of Object.values(LIBRARIES))
      if (groups.includes(group) && own[link] === null && !groups.some((key) => own[key]))
        delete own[link];
    this.#dropEmptySlideStyle(scope);
  }
  // Drops the scope's own start and end colors and gradient.
  resetBackground(scope = "slide", { restoreInheritance = true } = {}) {
    for (const key of ["top", "bottom"]) this.resetColor(key, scope, { restoreInheritance });
    if (restoreInheritance) {
      this.resetStyleGroup("gradient", scope);
      return;
    }
    delete this.writableStyle(scope).gradient;
    this.#dropEmptySlideStyle(scope);
  }
  // Drops every value the scope overrides on top of its palette.
  resetPalette(scope = "slide") {
    for (const group of LIBRARIES.palette.groups) this.resetStyleGroup(group, scope);
  }

  // "" inherits, "custom" keeps own colors, "style:<id>" links a palette. An unlinked project
  // default is "starter:<id>" of the default palette, which its own colors change.
  paletteValue(scope) {
    const own = this.ownStyle(scope);
    if (own.colorStyle) return `style:${own.colorStyle}`;
    if (own.colorStyle === null) return "custom";
    return scope === "project" ? `starter:${this.defaultPalette}` : "";
  }
  // "starter:<id>" copies that starter into the project's palettes and links the copy; the
  // project default goes back to the built-in colors for the default starter.
  setPalette(scope, value) {
    const [kind, id] = value.split(":");
    if (kind === "custom") return;
    if (kind === "style") this.#savedStyle("palette", id);
    const builtIn = kind === "starter" && scope === "project" && id === this.defaultPalette;
    const link = kind === "starter" && !builtIn ? this.#starterStyle(id) : id;
    const own = this.writableStyle(scope);
    for (const group of LIBRARIES.palette.groups) delete own[group];
    delete own.colorStyle;
    if (!builtIn) own.colorStyle = link;
    this.#dropEmptySlideStyle(scope);
  }
  // The project palette with the starter's colors and no gradient, added when missing.
  #starterStyle(id) {
    const colors = this.starterPalettes[id];
    if (!colors) throw new Error("Starter palette no longer exists.");
    const same = (style) =>
      !style.gradient &&
      Object.entries(colors).every(([key, color]) => style.colors[key] === color);
    return (
      this.project.colorStyles?.find(same)?.id ??
      this.addSavedStyle("palette", title(id), { colors: { ...colors } })
    );
  }
  // "" inherits, "builtin" uses the built-in layout, "style:<id>" links a layout template.
  layoutValue(scope) {
    const own = this.ownStyle(scope);
    if (own.layoutStyle) return `style:${own.layoutStyle}`;
    return scope === "project" || own.layoutStyle === null ? "builtin" : "";
  }
  setLayoutStyle(scope, value) {
    const [kind, id] = value.split(":");
    if (kind === "style") this.#savedStyle("layout", id);
    const own = this.writableStyle(scope);
    delete own.layoutSettings;
    delete own.layoutStyle;
    if (kind === "style") own.layoutStyle = id;
    if (kind === "builtin" && scope !== "project") own.layoutStyle = null;
    this.#dropEmptySlideStyle(scope);
  }
  resetColor(key, scope = "slide", { restoreInheritance = true } = {}) {
    const own = this.writableStyle(scope);
    if (own.colors && Object.hasOwn(own.colors, key)) {
      delete own.colors[key];
      if (restoreInheritance && own.colorStyle === null) delete own.colorStyle;
      if (!Object.keys(own.colors).length) delete own.colors;
    }
    this.#dropEmptySlideStyle(scope);
  }

  nextStyleName(kind) {
    const { list, noun } = LIBRARIES[kind],
      styles = this.project[list] || [];
    const names = new Set(styles.map((style) => style.name));
    let number = styles.length + 1;
    while (names.has(`${noun} ${number}`)) number++;
    return `${noun} ${number}`;
  }
  #savedStyle(kind, id) {
    const { list, noun } = LIBRARIES[kind];
    const saved = this.project[list]?.find((item) => item.id === id);
    if (!saved) throw new Error(`${noun} no longer exists.`);
    return saved;
  }
  #newStyleId(kind) {
    const { list, link, plural } = LIBRARIES[kind];
    this.project[list] ??= [];
    const styles = this.project[list],
      prefix = words(link).replaceAll(" ", "-");
    if (this.isFull(list))
      throw new Error(`Project supports at most ${this.limitOf(list)} ${plural}.`);
    let number = 1;
    while (styles.some((item) => item.id === `${prefix}-${number}`)) number++;
    return `${prefix}-${number}`;
  }
  // `entry` holds the library's value groups, such as `{ colors, gradient }`.
  addSavedStyle(kind, name, entry) {
    const { list, noun } = LIBRARIES[kind],
      id = this.#newStyleId(kind);
    this.project[list].push({
      id,
      name: styleName(name, noun),
      ...structuredClone(entryOf(kind, entry)),
    });
    return id;
  }
  // Saves the scope's values as a new library entry and links it in their place.
  saveSavedStyle(kind, name, entry, scope = "slide") {
    const { link, groups } = LIBRARIES[kind],
      id = this.addSavedStyle(kind, name, entry),
      own = this.writableStyle(scope);
    own[link] = id;
    for (const group of groups) delete own[group];
    return id;
  }
  // Renames the entry and replaces the groups `entry` holds; an empty group is removed.
  updateSavedStyle(kind, id, name, entry = {}) {
    const { noun, groups } = LIBRARIES[kind],
      saved = this.#savedStyle(kind, id);
    saved.name = styleName(name, noun);
    for (const group of groups) {
      if (!Object.hasOwn(entry, group)) continue;
      if (Object.keys(entry[group]).length) saved[group] = structuredClone(entry[group]);
      else delete saved[group];
    }
  }
  duplicateSavedStyle(kind, id) {
    const { list } = LIBRARIES[kind],
      source = this.#savedStyle(kind, id),
      copyId = this.#newStyleId(kind);
    // Leaves room for " copy N" and never splits a surrogate pair.
    const base = source.name.slice(0, 190).replace(/[\uD800-\uDBFF]$/, "");
    let name = `${base} copy`,
      suffix = 2;
    while (this.project[list].some((item) => item.name === name)) name = `${base} copy ${suffix++}`;
    this.project[list].push({ ...structuredClone(source), id: copyId, name });
    return copyId;
  }
  // Each slide and variant that links the entry, with the fields it overrides locally.
  savedStyleUsage(kind, id) {
    const { link, groups } = LIBRARIES[kind];
    return this.project.slides.flatMap((slide) =>
      this.variants.flatMap((variant) => {
        const layers = this.#layers(slide, variant);
        if (this.resolveStyle(layers)[link] !== id) return [];
        let local = {};
        for (const layer of layers) {
          if (Object.hasOwn(layer, link)) local = {};
          for (const group of groups) Object.assign(local, layer[group]);
        }
        return [{ slide: slide.id, variant: variant.id, overrides: Object.keys(local) }];
      }),
    );
  }
  // Scopes that linked a deleted entry keep its values as their own.
  deleteSavedStyle(kind, id) {
    const { list, link, groups } = LIBRARIES[kind],
      saved = this.project[list]?.find((item) => item.id === id);
    if (!saved) return;
    for (const scope of this.#styleScopes())
      if (scope[link] === id) {
        scope[link] = null;
        for (const group of groups)
          if (saved[group] || scope[group]) scope[group] = { ...saved[group], ...scope[group] };
      }
    this.project[list] = this.project[list].filter((item) => item.id !== id);
  }

  // One path may serve every locale, or each locale has its own screenshot.
  assetPath(platform) {
    const asset = this.slide.assets[platform];
    return typeof asset === "string"
      ? asset
      : asset && Object.hasOwn(asset, this.selection.locale)
        ? asset[this.selection.locale]
        : undefined;
  }
  setAsset(platform, path) {
    const asset = this.slide.assets[platform];
    if (asset && typeof asset === "object")
      this.slide.assets[platform] = { ...asset, [this.selection.locale]: path };
    else this.slide.assets[platform] = path;
  }
  // Slides (1-based numbers) without the platform's screenshot in at least one language.
  missingScreenshots(platform) {
    return this.project.slides.flatMap((slide, index) => {
      const asset = slide.assets[platform];
      const complete =
        typeof asset === "string"
          ? !!asset
          : this.project.locales.every(
              (locale) => asset && Object.hasOwn(asset, locale) && !!asset[locale],
            );
      return complete ? [] : [index + 1];
    });
  }
  // Gives the slides that lack the platform's screenshot these images, in slide order.
  addScreenshots(platform, paths) {
    const missing = this.missingScreenshots(platform);
    paths.slice(0, missing.length).forEach((path, index) => {
      const assets = this.project.slides[missing[index] - 1].assets,
        asset = assets[platform];
      assets[platform] =
        asset && typeof asset === "object"
          ? {
              ...asset,
              ...Object.fromEntries(
                this.project.locales
                  .filter((locale) => !Object.hasOwn(asset, locale) || !asset[locale])
                  .map((locale) => [locale, path]),
              ),
            }
          : path;
    });
    return Math.min(paths.length, missing.length);
  }

  // Adds a size beside its platform's other sizes, so exports and menus keep them together,
  // and previews it.
  addTarget(id) {
    const target = this.targetOf(id);
    if (!target) throw new Error("Unknown size.");
    const { targets } = this.project;
    if (!targets.includes(id)) {
      const platform = (other) => this.targetOf(other)?.platform;
      const last = targets.findLastIndex((other) => platform(other) === target.platform);
      targets.splice(last < 0 ? targets.length : last + 1, 0, id);
    }
    this.selection.target = id;
    this.#keepTargets();
  }

  // The last size stays: a project always exports something.
  removeTarget(id) {
    if (this.project.targets.length === 1) return;
    this.project.targets = this.project.targets.filter((other) => other !== id);
    this.#keepTargets();
  }

  // A new platform starts with a size in a required display group, preferring portrait.
  // `catalog` is the snapshot catalog with its targets and display groups.
  addPlatform(platform, { targets, displayGroups: groups }) {
    const required = new Set(groups.filter((group) => group.required).map((group) => group.id));
    const rank = (target) =>
      (target.displayGroups.some((id) => required.has(id)) ? 0 : 2) +
      (target.orientation === "landscape" ? 1 : 0);
    const sizes = targets.filter((target) => target.platform === platform);
    const [first] = sizes.sort((a, b) => rank(a) - rank(b));
    this.addTarget(first.id);
  }

  // A size outside the catalog: the screenshot as is, without a device mockup.
  addCustomSize(width, height) {
    const [low, high] = this.customSides;
    const valid = (side) => Number.isInteger(side) && side >= low && side <= high;
    if (!valid(width) || !valid(height))
      throw new Error(`Width and height must be whole pixels from ${low} to ${high}.`);
    if (width * height > this.customMaxPixels)
      throw new Error(
        `Custom sizes must contain at most ${this.customMaxPixels / 1_000_000} million pixels.`,
      );
    this.addTarget(`custom.${width}x${height}`);
  }

  // Keeps the previewed size and every explicit layout valid for the remaining sizes.
  #keepTargets() {
    if (!this.project.targets.includes(this.selection.target))
      this.selection.target = this.project.targets[0];
    autoUnsupportedLayouts(this.#styleScopes(), this.project.targets.map(this.targetOf));
  }

  #nextSlideId() {
    let number = 1;
    while (this.project.slides.some((slide) => slide.id === `slide-${number}`)) number++;
    return `slide-${number}`;
  }
  #uniqueSlideName(base) {
    const names = new Set(this.project.slides.map((slide) => slide.name));
    let name = base,
      suffix = 2;
    while (names.has(name)) {
      const ending = ` ${suffix++}`;
      name = `${[...base].slice(0, 200 - ending.length).join("")}${ending}`;
    }
    return name;
  }
  #nextSlideName() {
    const names = new Set(this.project.slides.map((slide) => slide.name));
    let number = this.project.slides.length + 1;
    while (names.has(`Slide ${number}`)) number++;
    return `Slide ${number}`;
  }
  #insertSlide(slide) {
    const slides = this.project.slides;
    slides.splice(slides.indexOf(this.slide) + 1, 0, slide);
    this.selection.slide = slide.id;
    return slide;
  }
  // A new slide inherits the project appearance and reuses the current screenshots.
  addSlide() {
    if (this.isFull("slides")) return;
    const copy = Object.fromEntries(
      this.project.locales.map((locale) => [locale, { headline: "Your headline" }]),
    );
    return this.#insertSlide({
      id: this.#nextSlideId(),
      name: this.#nextSlideName(),
      copy,
      assets: {},
    });
  }
  duplicateSlide() {
    if (this.isFull("slides")) return;
    const slide = structuredClone(this.slide);
    slide.id = this.#nextSlideId();
    slide.name = this.#uniqueSlideName(`${[...this.slideName].slice(0, 195).join("")} copy`);
    return this.#insertSlide(slide);
  }
  removeSlide() {
    const slides = this.project.slides;
    if (slides.length <= 1) return;
    const index = slides.indexOf(this.slide);
    slides.splice(index, 1);
    this.selection.slide = slides[Math.min(index, slides.length - 1)].id;
  }
  moveSlide(direction) {
    const slides = this.project.slides,
      index = slides.indexOf(this.slide),
      next = index + direction;
    if (next < 0 || next >= slides.length) return;
    [slides[index], slides[next]] = [slides[next], slides[index]];
  }
}

const selects = (selection) => (file) =>
  Object.entries(selection).every(([key, value]) => file[key] === value);

export function previewIndex(files, selection) {
  const index = files.findIndex(selects(selection));
  if (index < 0) throw new Error("The selected screenshot is not in the project plan.");
  return index;
}

// The plan entry of the selected slide, language, size and variant, if planned.
export function planEntry(files, selection) {
  return files.find(selects(selection));
}

// Slide thumbnails share the previewed locale, size and variant; unchanged ones are kept.
export function thumbnailJobs(files, selection, rendered) {
  const shown = (file) =>
    ["locale", "target", "variant"].every((key) => file[key] === selection[key]);
  return files.flatMap((file, index) => {
    const key = JSON.stringify(file);
    return shown(file) && rendered.get(file.slide) !== key
      ? [{ index, slide: file.slide, key }]
      : [];
  });
}
