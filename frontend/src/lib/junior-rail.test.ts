import assert from "node:assert/strict";
import test from "node:test";
import {
  JUNIOR_RAIL_DEFAULT,
  JUNIOR_RAIL_HIDDEN,
  JUNIOR_RAIL_SHOWN,
  JUNIOR_RAIL_STORAGE_KEY,
  loadJuniorRailFlags,
  parseJuniorRailFlags,
  patchJuniorRailFlags,
  saveJuniorRailFlags,
} from "./junior-rail";

test("junior rail defaults to all three panels visible", () => {
  assert.deepEqual(parseJuniorRailFlags(null), JUNIOR_RAIL_DEFAULT);
  assert.deepEqual(parseJuniorRailFlags(""), JUNIOR_RAIL_DEFAULT);
  assert.deepEqual(parseJuniorRailFlags(JUNIOR_RAIL_SHOWN), {
    showJobs: true,
    showMemory: true,
    showChats: true,
  });
});

test("legacy hidden rail maps to all three flags false", () => {
  assert.deepEqual(parseJuniorRailFlags(JUNIOR_RAIL_HIDDEN), {
    showJobs: false,
    showMemory: false,
    showChats: false,
  });
});

test("showJobs, showMemory, and showChats persist independently", () => {
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
    assert.deepEqual(loadJuniorRailFlags(), JUNIOR_RAIL_DEFAULT);
    saveJuniorRailFlags({ showJobs: false, showMemory: true, showChats: true });
    assert.equal(JSON.parse(store[JUNIOR_RAIL_STORAGE_KEY]).showJobs, false);
    assert.deepEqual(loadJuniorRailFlags(), { showJobs: false, showMemory: true, showChats: true });
    saveJuniorRailFlags({ showJobs: false, showMemory: false, showChats: true });
    assert.deepEqual(loadJuniorRailFlags(), { showJobs: false, showMemory: false, showChats: true });
    saveJuniorRailFlags({ showJobs: true, showMemory: false, showChats: false });
    assert.deepEqual(loadJuniorRailFlags(), { showJobs: true, showMemory: false, showChats: false });
  } finally {
    Object.defineProperty(globalThis, "localStorage", { configurable: true, value: original });
  }
});

test("patching one rail flag does not force the others", () => {
  const current = { showJobs: false, showMemory: true, showChats: true };
  assert.deepEqual(patchJuniorRailFlags(current, { showChats: false }), {
    showJobs: false,
    showMemory: true,
    showChats: false,
  });
  assert.deepEqual(patchJuniorRailFlags(current, { showJobs: true }), {
    showJobs: true,
    showMemory: true,
    showChats: true,
  });
  assert.deepEqual(parseJuniorRailFlags(JSON.stringify({ showJobs: false })), {
    showJobs: false,
    showMemory: true,
    showChats: true,
  });
});
