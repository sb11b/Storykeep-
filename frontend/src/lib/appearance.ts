import type { User } from "./types";

export type FontFamilyChoice = "serif" | "sans" | "source-serif" | "system";
export type BaseFontSize = "sm" | "md" | "lg";

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

export function appearanceFromPreferences(preferences: Record<string, unknown> | undefined): AppearanceSettings {
  const raw = (preferences?.appearance || {}) as Partial<AppearanceSettings>;
  return {
    page_preset: raw.page_preset || DEFAULT_APPEARANCE.page_preset,
    rail_preset: raw.rail_preset || DEFAULT_APPEARANCE.rail_preset,
    topbar_preset: raw.topbar_preset || DEFAULT_APPEARANCE.topbar_preset,
    page_custom: normalizeHex(raw.page_custom),
    rail_custom: normalizeHex(raw.rail_custom),
    topbar_custom: normalizeHex(raw.topbar_custom),
    font_family: FONT_FAMILY_OPTIONS.some((row) => row.value === raw.font_family)
      ? (raw.font_family as FontFamilyChoice)
      : DEFAULT_APPEARANCE.font_family,
    base_font_size: BASE_FONT_SIZE_OPTIONS.some((row) => row.value === raw.base_font_size)
      ? (raw.base_font_size as BaseFontSize)
      : DEFAULT_APPEARANCE.base_font_size,
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

  root.style.setProperty("--background", page);
  root.style.setProperty("--sidebar", rail);
  root.style.setProperty("--card", topbar);
  root.style.setProperty("--popover", topbar);
  root.style.setProperty("--storykeep-body-font", font);
  root.style.fontSize = size;
}

export function applyAppearanceFromUser(user: User | null | undefined) {
  applyAppearance(appearanceFromPreferences(user?.preferences));
}
