import assert from "node:assert/strict";
import test from "node:test";
import { startOfWeek, weekRange } from "./calendar-range";

test("week range is Sunday through next Sunday", () => {
  const wednesday = new Date(2026, 8, 16, 12, 0, 0);
  const start = startOfWeek(wednesday);
  assert.equal(start.getDay(), 0);
  assert.equal(start.getDate(), 13);
  const range = weekRange(wednesday);
  assert.equal(range.end.getDate(), 20);
});
