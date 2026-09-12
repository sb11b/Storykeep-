import assert from "node:assert/strict";
import test from "node:test";
import {
  appearanceFromPreferences,
  applyAppearance,
  baseFontSizePx,
  DEFAULT_APPEARANCE,
  fontFamilyCss,
  normalizeHex,
  resolvePresetColor,
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

test("appearanceFromPreferences merges defaults", () => {
  const settings = appearanceFromPreferences({
    appearance: { rail_preset: "navy", font_family: "serif", base_font_size: "lg" },
  });
  assert.equal(settings.rail_preset, "navy");
  assert.equal(settings.font_family, "serif");
  assert.equal(settings.base_font_size, "lg");
  assert.equal(settings.page_preset, DEFAULT_APPEARANCE.page_preset);
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
  };
  const previous = globalThis.document;
  globalThis.document = { documentElement: root } as Document;

  try {
    applyAppearance({
      ...DEFAULT_APPEARANCE,
      rail_custom: "#445566",
      font_family: "source-serif",
      base_font_size: "sm",
    });
    assert.equal(props["--sidebar"], "#445566");
    assert.match(props["--storykeep-body-font"], /source-serif/);
    assert.equal(root.style.fontSize, "14px");
  } finally {
    globalThis.document = previous;
  }
});
