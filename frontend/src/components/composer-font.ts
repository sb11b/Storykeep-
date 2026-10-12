"use client";

import { useEffect, useState } from "react";

/**
 * Fonts selectable in the note composer. The first four are built-in faces
 * already loaded by the app (see FONT_FAMILY_OPTIONS in @/lib/appearance);
 * uploaded fonts are registered at runtime from a data URL stored locally.
 */
export type ComposerFontChoice = "serif" | "sans" | "source-serif" | "system" | (string & {});

export const COMPOSER_FONT_OPTIONS: { value: string; label: string; css: string }[] = [
  { value: "serif", label: "Newsreader", css: 'var(--font-serif), "Iowan Old Style", serif' },
  { value: "sans", label: "Sans", css: "var(--font-sans), ui-sans-serif, sans-serif" },
  { value: "source-serif", label: "Source Serif", css: 'var(--font-source-serif), Georgia, serif' },
  { value: "system", label: "System", css: "system-ui, -apple-system, Segoe UI, sans-serif" },
];

const STORAGE_KEY = "storykeep-composer-fonts";
const FONT_CSS_ID = "sk-composer-font-faces";
const MAX_BYTES = 4 * 1024 * 1024;

export type CustomComposerFont = { id: string; label: string; dataUrl: string };

function fontCss(choice: string, customs: CustomComposerFont[]): string {
  const builtin = COMPOSER_FONT_OPTIONS.find((row) => row.value === choice);
  if (builtin) return builtin.css;
  const custom = customs.find((row) => row.id === choice);
  return custom ? `"sk-${custom.id}", sans-serif` : COMPOSER_FONT_OPTIONS[1].css;
}

/** @font-face rules for every uploaded font; injected once and kept in sync. */
function injectFaces(fonts: CustomComposerFont[]) {
  if (typeof document === "undefined") return;
  let el = document.getElementById(FONT_CSS_ID) as HTMLStyleElement | null;
  if (!el) {
    el = document.createElement("style");
    el.id = FONT_CSS_ID;
    document.head.appendChild(el);
  }
  el.textContent = fonts
    .map((font) => `@font-face{font-family:"sk-${font.id}";src:url(${font.dataUrl});}`)
    .join("\n");
}

export function readCustomFonts(): CustomComposerFont[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter(
      (row): row is CustomComposerFont =>
        !!row &&
        typeof row === "object" &&
        typeof (row as CustomComposerFont).id === "string" &&
        typeof (row as CustomComposerFont).dataUrl === "string",
    );
  } catch {
    return [];
  }
}

function writeCustomFonts(fonts: CustomComposerFont[]) {
  try {
    window.localStorage.setItem(STORAGE_KEY, JSON.stringify(fonts));
  } catch {
    /* quota or disabled — fonts still work for this session */
  }
}

/** Read a font file (.ttf/.otf/.woff/.woff2) and return a storable entry. */
export function readFontFile(file: File): Promise<CustomComposerFont> {
  return new Promise((resolve, reject) => {
    if (file.size > MAX_BYTES) {
      reject(new Error("Font file is too large (max 4 MB)."));
      return;
    }
    const reader = new FileReader();
    reader.onload = () => {
      const dataUrl = String(reader.result || "");
      if (!dataUrl.startsWith("data:")) {
        reject(new Error("Could not read that font file."));
        return;
      }
      const base = file.name.replace(/\.[^.]+$/, "").trim() || "Uploaded font";
      resolve({ id: `f${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`, label: base, dataUrl });
    };
    reader.onerror = () => reject(new Error("Could not read that font file."));
    reader.readAsDataURL(file);
  });
}

/**
 * Composer font state: current choice, the full option list (built-ins +
 * uploads), and handlers for upload/remove. Persists uploads to
 * localStorage so the choice survives reloads on this device.
 */
export function useComposerFont() {
  const [choice, setChoice] = useState("sans");
  const [customs, setCustoms] = useState<CustomComposerFont[]>([]);

  useEffect(() => {
    const stored = readCustomFonts();
    setCustoms(stored);
    injectFaces(stored);
    const storedChoice = (() => {
      try {
        return window.localStorage.getItem(`${STORAGE_KEY}-choice`);
      } catch {
        return null;
      }
    })();
    if (storedChoice) setChoice(storedChoice);
  }, []);

  function select(next: string) {
    setChoice(next);
    try {
      window.localStorage.setItem(`${STORAGE_KEY}-choice`, next);
    } catch {
      /* ignore */
    }
  }

  function add(file: File): Promise<string> {
    return readFontFile(file).then((entry) => {
      const next = [...customs, entry];
      setCustoms(next);
      writeCustomFonts(next);
      injectFaces(next);
      select(entry.id);
      return entry.label;
    });
  }

  function remove(id: string) {
    const next = customs.filter((row) => row.id !== id);
    setCustoms(next);
    writeCustomFonts(next);
    injectFaces(next);
    if (choice === id) select("sans");
  }

  return {
    choice,
    css: fontCss(choice, customs),
    options: [...COMPOSER_FONT_OPTIONS, ...customs.map((row) => ({ value: row.id, label: row.label, css: `"sk-${row.id}"` }))],
    select,
    add,
    remove,
  };
}
