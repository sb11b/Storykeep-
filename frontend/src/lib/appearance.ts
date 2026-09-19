import type { User } from "./types";

export type FontFamilyChoice = "serif" | "sans" | "source-serif" | "system";
export type BaseFontSize = "sm" | "md" | "lg";

export type ThemeColorChoice = {
  preset: string;
  custom: string | null;
};

export type AppearanceSettings = {
  page_preset: string;
  rail_preset: string;
  topbar_preset: string;
  page_custom: string | null;
  rail_custom: string | null;
  topbar_custom: string | null;
  font_family: FontFamilyChoice;
  base_font_size: BaseFontSize;
};

export const DEFAULT_APPEARANCE: AppearanceSettings = {
  page_preset: "paper",
  rail_preset: "dark-oak",
  topbar_preset: "paper",
  page_custom: null,
  rail_custom: null,
  topbar_custom: null,
  font_family: "sans",
  base_font_size: "md",
};

export const PAGE_COLOR_PRESETS: Record<string, string> = {
  paper: "oklch(0.965 0.018 88)",
  cream: "oklch(0.97 0.025 92)",
  white: "oklch(0.995 0.005 95)",
  slate: "oklch(0.94 0.012 250)",
};

export const RAIL_COLOR_PRESETS: Record<string, string> = {
  "dark-oak": "oklch(0.23 0.02 55)",
  charcoal: "oklch(0.28 0.015 260)",
  forest: "oklch(0.26 0.04 150)",
  navy: "oklch(0.24 0.04 260)",
};

export const TOPBAR_COLOR_PRESETS: Record<string, string> = {
  paper: "oklch(0.985 0.01 88)",
  cream: "oklch(0.975 0.015 90)",
  white: "oklch(1 0 0)",
  slate: "oklch(0.96 0.01 250)",
};

export const FONT_FAMILY_OPTIONS: { value: FontFamilyChoice; label: string; css: string }[] = [
  { value: "serif", label: "Newsreader", css: 'var(--font-serif), "Iowan Old Style", serif' },
  { value: "sans", label: "Sans", css: 'var(--font-sans), ui-sans-serif, sans-serif' },
  { value: "source-serif", label: "Source Serif", css: 'var(--font-source-serif), Georgia, serif' },
  { value: "system", label: "System", css: "system-ui, -apple-system, Segoe UI, sans-serif" },
];

export const BASE_FONT_SIZE_OPTIONS: { value: BaseFontSize; label: string; px: string }[] = [
  { value: "sm", label: "S", px: "14px" },
  { value: "md", label: "Normal", px: "16px" },
  { value: "lg", label: "L", px: "18px" },
];

export const FONT_PREVIEW_SAMPLE =
  "The quick brown fox jumps over 123 lazy dogs. Aa Bb Cc — \"Hello!\" (?)";

export function fontFamilyCss(family: FontFamilyChoice): string {
  return FONT_FAMILY_OPTIONS.find((row) => row.value === family)?.css || FONT_FAMILY_OPTIONS[1].css;
}

export function baseFontSizePx(size: BaseFontSize): string {
  return BASE_FONT_SIZE_OPTIONS.find((row) => row.value === size)?.px || "16px";
}

const HEX_RE = /^#[0-9a-fA-F]{6}$/;

export function normalizeHex(value: string | null | undefined): string | null {
  const trimmed = (value || "").trim();
  if (!trimmed) return null;
  const withHash = trimmed.startsWith("#") ? trimmed : `#${trimmed}`;
  return HEX_RE.test(withHash) ? withHash.toLowerCase() : null;
}

export function resolvePresetColor(
  preset: string,
  custom: string | null | undefined,
  presets: Record<string, string>,
  fallback: string,
): string {
  const hex = normalizeHex(custom);
  if (hex) return hex;
  return presets[preset] || presets[fallback] || Object.values(presets)[0];
}

function readThemeColor(
  raw: Record<string, unknown>,
  nestedKey: "pageBg" | "topBar" | "rail",
  presetDefault: string,
  customDefault: string | null,
  flatPresetKey: keyof AppearanceSettings,
  flatCustomKey: keyof AppearanceSettings,
): ThemeColorChoice {
  const nested = raw[nestedKey];
  if (nested && typeof nested === "object") {
    const row = nested as { preset?: string; custom?: string | null };
    return {
      preset: row.preset || presetDefault,
      custom: normalizeHex(row.custom) ?? customDefault,
    };
  }
  const flatPreset = raw[flatPresetKey];
  const flatCustom = raw[flatCustomKey];
  return {
    preset: typeof flatPreset === "string" && flatPreset ? flatPreset : presetDefault,
    custom: normalizeHex(typeof flatCustom === "string" ? flatCustom : null) ?? customDefault,
  };
}

export function appearanceFromPreferences(preferences: Record<string, unknown> | undefined): AppearanceSettings {
  const raw = (preferences?.appearance || {}) as Record<string, unknown>;
  const page = readThemeColor(raw, "pageBg", DEFAULT_APPEARANCE.page_preset, null, "page_preset", "page_custom");
  const topBar = readThemeColor(raw, "topBar", DEFAULT_APPEARANCE.topbar_preset, null, "topbar_preset", "topbar_custom");
  const rail = readThemeColor(raw, "rail", DEFAULT_APPEARANCE.rail_preset, null, "rail_preset", "rail_custom");
  const fontFamily = raw.font_family;
  const baseFontSize = raw.base_font_size;
  return {
    page_preset: page.preset,
    page_custom: page.custom,
    topbar_preset: topBar.preset,
    topbar_custom: topBar.custom,
    rail_preset: rail.preset,
    rail_custom: rail.custom,
    font_family: FONT_FAMILY_OPTIONS.some((row) => row.value === fontFamily)
      ? (fontFamily as FontFamilyChoice)
      : DEFAULT_APPEARANCE.font_family,
    base_font_size: BASE_FONT_SIZE_OPTIONS.some((row) => row.value === baseFontSize)
      ? (baseFontSize as BaseFontSize)
      : DEFAULT_APPEARANCE.base_font_size,
  };
}

/** Payload for PATCH /api/v1/me — pageBg, topBar, and rail stored together. */
export function surfaceIsDark(color: string): boolean {
  const oklch = color.match(/oklch\(\s*([0-9.]+)/i);
  if (oklch) return parseFloat(oklch[1]) < 0.55;
  const hex = normalizeHex(color);
  if (hex) {
    const r = parseInt(hex.slice(1, 3), 16);
    const g = parseInt(hex.slice(3, 5), 16);
    const b = parseInt(hex.slice(5, 7), 16);
    const lum = (0.299 * r + 0.587 * g + 0.114 * b) / 255;
    return lum < 0.45;
  }
  return false;
}

export function appearanceToMePatch(settings: AppearanceSettings): Record<string, unknown> {
  return {
    pageBg: { preset: settings.page_preset, ...(settings.page_custom ? { custom: settings.page_custom } : {}) },
    topBar: { preset: settings.topbar_preset, ...(settings.topbar_custom ? { custom: settings.topbar_custom } : {}) },
    rail: { preset: settings.rail_preset, ...(settings.rail_custom ? { custom: settings.rail_custom } : {}) },
    font_family: settings.font_family,
    base_font_size: settings.base_font_size,
  };
}

export function applyAppearance(settings: AppearanceSettings) {
  if (typeof document === "undefined") return;
  const root = document.documentElement;
  const page = resolvePresetColor(settings.page_preset, settings.page_custom, PAGE_COLOR_PRESETS, "paper");
  const rail = resolvePresetColor(settings.rail_preset, settings.rail_custom, RAIL_COLOR_PRESETS, "dark-oak");
  const topbar = resolvePresetColor(settings.topbar_preset, settings.topbar_custom, TOPBAR_COLOR_PRESETS, "paper");
  const font = FONT_FAMILY_OPTIONS.find((row) => row.value === settings.font_family)?.css || FONT_FAMILY_OPTIONS[1].css;
  const size = BASE_FONT_SIZE_OPTIONS.find((row) => row.value === settings.base_font_size)?.px || "16px";

  const darkPage = surfaceIsDark(page);
  const darkTopbar = surfaceIsDark(topbar);
  const pageFg = darkPage ? "oklch(0.93 0.02 88)" : "oklch(0.24 0.02 55)";
  const pageMuted = darkPage ? "oklch(0.74 0.03 80)" : "oklch(0.5 0.03 55)";
  const topbarFg = darkTopbar ? "oklch(0.93 0.02 88)" : "#3f3a32";
  const topbarFgMuted = darkTopbar ? "oklch(0.74 0.03 80)" : "#6f6a62";
  const topbarHover = darkTopbar ? "oklch(1 0 0 / 10%)" : "#f3efe6";

  root.style.setProperty("--storykeep-page-bg", page);
  root.style.setProperty("--storykeep-top-bar", topbar);
  root.style.setProperty("--storykeep-top-bar-fg", topbarFg);
  root.style.setProperty("--storykeep-top-bar-fg-muted", topbarFgMuted);
  root.style.setProperty("--storykeep-top-bar-hover", topbarHover);
  root.style.setProperty("--storykeep-rail", rail);
  root.style.setProperty("--storykeep-page-fg", pageFg);
  root.style.setProperty("--storykeep-page-muted", pageMuted);
  // Reader surfaces use --storykeep-* via .sk-page-surface. Leave global shadcn
  // tokens (--popover, --background, …) to light/dark CSS so Junior follows the OS.
  root.style.setProperty("--storykeep-body-font", font);
  root.style.fontSize = size;
  root.dataset.pageTheme = darkPage ? "dark" : "light";
}

export function applyAppearanceFromUser(user: User | null | undefined) {
  applyAppearance(appearanceFromPreferences(user?.preferences));
}
