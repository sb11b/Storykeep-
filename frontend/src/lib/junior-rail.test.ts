import assert from "node:assert/strict";
import test from "node:test";
import {
  JUNIOR_RAIL_HIDDEN,
  JUNIOR_RAIL_SHOWN,
  JUNIOR_RAIL_STORAGE_KEY,
  loadJuniorRailHidden,
  saveJuniorRailHidden,
} from "./junior-rail";

test("junior rail remembers hidden vs shown in localStorage", () => {
  const store: Record<string, string> = {};
  const original = globalThis.localStorage;
  Object.defineProperty(globalThis, "localStorage", {
    configurable: true,
    value: {
      getItem: (key: string) => store[key] ?? null,
      setItem: (key: string, value: string) => {
        store[key] = value;
      },
    },
  });
  try {
    assert.equal(loadJuniorRailHidden(), false);
    saveJuniorRailHidden(true);
    assert.equal(store[JUNIOR_RAIL_STORAGE_KEY], JUNIOR_RAIL_HIDDEN);
    assert.equal(loadJuniorRailHidden(), true);
    saveJuniorRailHidden(false);
    assert.equal(store[JUNIOR_RAIL_STORAGE_KEY], JUNIOR_RAIL_SHOWN);
    assert.equal(loadJuniorRailHidden(), false);
  } finally {
    Object.defineProperty(globalThis, "localStorage", { configurable: true, value: original });
  }
});
