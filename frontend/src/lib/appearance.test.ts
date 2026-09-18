import assert from "node:assert/strict";
import test from "node:test";
import {
  appearanceFromPreferences,
  appearanceToMePatch,
  applyAppearance,
  baseFontSizePx,
  DEFAULT_APPEARANCE,
  fontFamilyCss,
  normalizeHex,
  resolvePresetColor,
  surfaceIsDark,
  PAGE_COLOR_PRESETS,
} from "./appearance";

test("normalizeHex accepts 6-digit hex with or without hash", () => {
  assert.equal(normalizeHex("#AABBCC"), "#aabbcc");
  assert.equal(normalizeHex("aabbcc"), "#aabbcc");
  assert.equal(normalizeHex("bad"), null);
  assert.equal(normalizeHex(""), null);
});

test("resolvePresetColor prefers custom hex over preset", () => {
  const color = resolvePresetColor("paper", "#112233", PAGE_COLOR_PRESETS, "paper");
  assert.equal(color, "#112233");
});

test("fontFamilyCss and baseFontSizePx resolve choices", () => {
  assert.match(fontFamilyCss("source-serif"), /source-serif/);
  assert.equal(baseFontSizePx("sm"), "14px");
  assert.equal(baseFontSizePx("lg"), "18px");
});

test("appearanceFromPreferences reads pageBg and topBar", () => {
  const settings = appearanceFromPreferences({
    appearance: {
      pageBg: { preset: "cream" },
      topBar: { preset: "slate" },
      rail: { preset: "navy" },
      font_family: "serif",
      base_font_size: "lg",
    },
  });
  assert.equal(settings.page_preset, "cream");
  assert.equal(settings.topbar_preset, "slate");
  assert.equal(settings.rail_preset, "navy");
});

test("appearanceFromPreferences merges defaults", () => {
  const settings = appearanceFromPreferences({
    appearance: { rail: { preset: "navy" }, font_family: "serif", base_font_size: "lg" },
  });
  assert.equal(settings.rail_preset, "navy");
  assert.equal(settings.font_family, "serif");
  assert.equal(settings.base_font_size, "lg");
  assert.equal(settings.page_preset, DEFAULT_APPEARANCE.page_preset);
});

test("surfaceIsDark detects dark page colors", () => {
  assert.equal(surfaceIsDark("oklch(0.2 0.02 55)"), true);
  assert.equal(surfaceIsDark("oklch(0.96 0.02 88)"), false);
  assert.equal(surfaceIsDark("#111111"), true);
});

test("appearanceToMePatch includes pageBg topBar and rail", () => {
  const payload = appearanceToMePatch({
    ...DEFAULT_APPEARANCE,
    page_preset: "cream",
    topbar_preset: "white",
    rail_preset: "forest",
  });
  assert.deepEqual(payload.pageBg, { preset: "cream" });
  assert.deepEqual(payload.topBar, { preset: "white" });
  assert.deepEqual(payload.rail, { preset: "forest" });
});

test("applyAppearance sets CSS variables on document root", () => {
  const props: Record<string, string> = {};
  const root = {
    style: {
      fontSize: "",
      setProperty: (name: string, value: string) => {
        props[name] = value;
      },
    },
    dataset: {} as DOMStringMap,
  };
  const previous = globalThis.document;
  globalThis.document = { documentElement: root } as Document;

  try {
    applyAppearance({
      ...DEFAULT_APPEARANCE,
      page_custom: "#111122",
      topbar_custom: "#334455",
      rail_custom: "#445566",
      font_family: "source-serif",
      base_font_size: "sm",
    });
    assert.equal(props["--storykeep-page-bg"], "#111122");
    assert.equal(props["--storykeep-page-fg"], "oklch(0.93 0.02 88)");
    assert.equal(props["--storykeep-page-muted"], "oklch(0.74 0.03 80)");
    assert.equal(props["--storykeep-top-bar"], "#334455");
    assert.equal(props["--storykeep-rail"], "#445566");
    assert.equal(props["--foreground"], undefined);
    assert.equal(props["--background"], undefined);
    assert.match(props["--storykeep-body-font"], /source-serif/);
    assert.equal(root.style.fontSize, "14px");
  } finally {
    globalThis.document = previous;
  }
});
