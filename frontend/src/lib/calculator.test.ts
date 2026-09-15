import assert from "node:assert/strict";
import test from "node:test";
import { evaluateExpression, looksLikeSchoolPaper, pushCalcHistory } from "./calculator";
import { clampCalcBox, defaultCalcBubblePos, CALC_MIN_H, CALC_MIN_W } from "./calculator-layout";

test("2^10 is 1024", () => {
  const result = evaluateExpression("2^10", "deg");
  assert.equal(result.ok, true);
  if (result.ok) assert.equal(result.display, "1024");
});

test("sin(30°) and sin(30) are 0.5 in deg mode", () => {
  const withMark = evaluateExpression("sin(30°)", "deg");
  const plain = evaluateExpression("sin(30)", "deg");
  assert.equal(withMark.ok, true);
  assert.equal(plain.ok, true);
  if (withMark.ok) assert.equal(withMark.display, "0.5");
  if (plain.ok) assert.equal(plain.display, "0.5");
});

test("rad mode still honors the degree mark", () => {
  const result = evaluateExpression("sin(30°)", "rad");
  assert.equal(result.ok, true);
  if (result.ok) assert.equal(result.display, "0.5");
});

test("standard ops, percent, factorial, and 1/x", () => {
  const add = evaluateExpression("1+2×3", "deg");
  assert.equal(add.ok, true);
  if (add.ok) assert.equal(add.display, "7");
  const pct = evaluateExpression("50%", "deg");
  assert.equal(pct.ok, true);
  if (pct.ok) assert.equal(pct.display, "0.5");
  const fact = evaluateExpression("5!", "deg");
  assert.equal(fact.ok, true);
  if (fact.ok) assert.equal(fact.display, "120");
  const inv = evaluateExpression("inv(4)", "deg");
  assert.equal(inv.ok, true);
  if (inv.ok) assert.equal(inv.display, "0.25");
});

test("does not evaluate pasted school papers", () => {
  assert.equal(looksLikeSchoolPaper("Explain this homework paragraph because the slope is two."), true);
  assert.equal(looksLikeSchoolPaper("line one\nline two"), true);
  assert.equal(evaluateExpression("Please explain this assignment in detail.", "deg").ok, false);
  assert.equal(evaluateExpression("2^10", "deg").ok, true);
});

test("history keeps the last 20 locally", () => {
  let items = [];
  for (let i = 0; i < 25; i += 1) {
    items = pushCalcHistory(items, { expr: `${i}`, result: `${i}` });
  }
  assert.equal(items.length, 20);
  assert.equal(items[0]?.expr, "24");
});

test("calculator bubble defaults left of Junior's bottom-right corner", () => {
  const pos = defaultCalcBubblePos(1000, 800);
  assert.equal(pos.x < 1000 - 72, true);
  assert.equal(pos.y, 800 - 72);
});

test("calculator panel stays on screen", () => {
  const box = clampCalcBox({ left: -40, top: 4000, w: 80, h: 80 }, 1000, 800);
  assert.equal(box.w, CALC_MIN_W);
  assert.equal(box.h, CALC_MIN_H);
  assert.equal(box.left >= 8, true);
  assert.equal(box.top + box.h <= 800 - 8, true);
});
