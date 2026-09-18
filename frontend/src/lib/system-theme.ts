"use client";

import { useEffect, useState } from "react";

export type SystemColorScheme = "light" | "dark";

export function readSystemColorScheme(): SystemColorScheme {
  if (typeof window === "undefined") return "light";
  return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
}

/** Live OS light/dark preference — used by Junior surfaces and menus. */
export function useSystemColorScheme(): SystemColorScheme {
  const [scheme, setScheme] = useState<SystemColorScheme>("light");

  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const sync = () => setScheme(media.matches ? "dark" : "light");
    sync();
    media.addEventListener("change", sync);
    return () => media.removeEventListener("change", sync);
  }, []);

  return scheme;
}

export function systemPrefersDark(): boolean {
  return readSystemColorScheme() === "dark";
}
