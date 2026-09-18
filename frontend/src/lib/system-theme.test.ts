import assert from "node:assert/strict";
import test from "node:test";
import { readSystemColorScheme } from "./system-theme";

test("readSystemColorScheme follows prefers-color-scheme", () => {
  const previous = globalThis.window;
  globalThis.window = {
    matchMedia: (query: string) => ({
      matches: query.includes("dark"),
      addEventListener: () => {},
      removeEventListener: () => {},
    }),
  } as Window & typeof globalThis;

  try {
    assert.equal(readSystemColorScheme(), "dark");
  } finally {
    globalThis.window = previous;
  }
});
