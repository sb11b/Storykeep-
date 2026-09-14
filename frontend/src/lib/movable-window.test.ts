import assert from "node:assert/strict";
import test from "node:test";
import {
  clampWindowPoint,
  defaultAddNotesPos,
  parseStoredPoint,
  shouldStartWindowDrag,
  WINDOW_MARGIN,
} from "./movable-window";

test("clampWindowPoint keeps the box on screen", () => {
  const next = clampWindowPoint(-80, 4000, 280, 200, 1000, 800);
  assert.equal(next.x, WINDOW_MARGIN);
  assert.equal(next.y + 200 <= 800 - WINDOW_MARGIN, true);
});

test("clampWindowPoint does not push a wide box off the left edge", () => {
  const next = clampWindowPoint(900, 10, 400, 180, 1000, 800);
  assert.equal(next.x + 400 <= 1000 - WINDOW_MARGIN, true);
  assert.equal(next.x >= WINDOW_MARGIN, true);
});

test("default Add to notes position sits on the left, not over a right-hand Junior pane", () => {
  const pos = defaultAddNotesPos(1280, 800, 300, 240);
  assert.equal(pos.x < 80, true);
  assert.equal(pos.y + 240 <= 800, true);
});

test("parseStoredPoint reads last x,y", () => {
  assert.deepEqual(parseStoredPoint('{"x":120,"y":40}'), { x: 120, y: 40 });
  assert.equal(parseStoredPoint("nope"), null);
  assert.equal(parseStoredPoint('{"x":"1","y":2}'), null);
});

test("shouldStartWindowDrag only from the title handle, not inputs or selects", () => {
  assert.equal(shouldStartWindowDrag(true, false), true);
  assert.equal(shouldStartWindowDrag(true, true), false);
  assert.equal(shouldStartWindowDrag(false, false), false);
});
