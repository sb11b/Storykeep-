import assert from "node:assert/strict";
import test from "node:test";
import { MIC_TOGGLE_DEBOUNCE_MS } from "@/components/junior-mic";

test("mic toggle debounce is 300ms", () => {
  assert.equal(MIC_TOGGLE_DEBOUNCE_MS, 300);
});
