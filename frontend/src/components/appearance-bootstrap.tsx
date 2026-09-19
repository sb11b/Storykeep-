"use client";

import { useLayoutEffect } from "react";
import { applyAppearance, DEFAULT_APPEARANCE } from "@/lib/appearance";

/** Apply StoryKeep surface colors before paint so the top bar never flashes wrong contrast. */
export function AppearanceBootstrap() {
  useLayoutEffect(() => {
    applyAppearance(DEFAULT_APPEARANCE);
  }, []);

  return null;
}
