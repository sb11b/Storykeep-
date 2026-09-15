import assert from "node:assert/strict";
import test from "node:test";
import { filingFromDropdowns, LAST_FILING_KEY, loadLastFiling, saveLastFiling } from "./last-filing";

test("empty dropdowns use last-used Junior / transfer block, not Inbox", () => {
  const store: Record<string, string> = {};
  const original = globalThis.window;
  (globalThis as { window?: Window & typeof globalThis }).window = {
    localStorage: {
      getItem: (key: string) => store[key] ?? null,
      setItem: (key: string, value: string) => {
        store[key] = value;
      },
      removeItem: (key: string) => {
        delete store[key];
      },
    },
  } as Window & typeof globalThis;
  try {
    const folderId = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";
    saveLastFiling("junior", folderId);
    assert.equal(loadLastFiling().dest, "junior");
    assert.equal(loadLastFiling().folderId, folderId);
    const empty = filingFromDropdowns("", null, [
      { id: folderId, shelf: "junior", name: "transfer block", item_count: 1, created_at: "" },
    ]);
    assert.equal(empty.dest, "junior");
    assert.equal(empty.folderId, folderId);
    assert.notEqual(empty.dest, "inbox");
    assert.match(store[LAST_FILING_KEY] || "", /junior/);
  } finally {
    if (original) (globalThis as { window?: Window & typeof globalThis }).window = original;
    else delete (globalThis as { window?: Window & typeof globalThis }).window;
  }
});
