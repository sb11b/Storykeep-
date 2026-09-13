import assert from "node:assert/strict";
import test from "node:test";
import {
  PANEL_MIN_H,
  PANEL_MIN_W,
  applyPanelResize,
  clampPanelBox,
  defaultPanelSize,
} from "./grok-panel-resize";

const start = { left: 100, top: 80, w: 600, h: 640 };

test("default panel size is larger than the old 380x520 smush", () => {
  const size = defaultPanelSize(1400, 900);
  assert.equal(size.w >= 600, true);
  assert.equal(size.h >= 680, true);
});

test("clampPanelBox keeps the panel on screen and above min size", () => {
  const box = clampPanelBox({ left: -40, top: 2000, w: 200, h: 200 }, 1000, 800);
  assert.equal(box.w, PANEL_MIN_W);
  assert.equal(box.h, PANEL_MIN_H);
  assert.equal(box.left >= 8, true);
  assert.equal(box.top + box.h <= 800 - 8, true);
});

test("southeast resize grows width and height", () => {
  const next = applyPanelResize(start, "se", 40, 30, 1400, 900);
  assert.equal(next.w, 640);
  assert.equal(next.h, 670);
  assert.equal(next.left, 100);
  assert.equal(next.top, 80);
});

test("west resize keeps the right edge fixed", () => {
  const next = applyPanelResize(start, "w", -50, 0, 1400, 900);
  assert.equal(next.w, 650);
  assert.equal(next.left + next.w, start.left + start.w);
});

test("north resize keeps the bottom edge fixed", () => {
  const next = applyPanelResize(start, "n", 0, -40, 1400, 900);
  assert.equal(next.h, 680);
  assert.equal(next.top + next.h, start.top + start.h);
});

test("min size stops a west shrink from eating the composer", () => {
  const next = applyPanelResize(start, "w", 400, 0, 1400, 900);
  assert.equal(next.w, PANEL_MIN_W);
  assert.equal(next.left + next.w, start.left + start.w);
});
