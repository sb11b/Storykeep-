import assert from "node:assert/strict";
import test from "node:test";
import {
  DEFAULT_PANE_NAME,
  chatStatusLine,
  defaultGrokPaneName,
  isDefaultPaneName,
} from "./grok-pane-name";

test("the default pane name is Junior", () => {
  assert.equal(DEFAULT_PANE_NAME, "Junior");
  assert.equal(defaultGrokPaneName(0), "Junior");
  assert.equal(defaultGrokPaneName(1), "Junior 2");
});

test("legacy Grok and Larry labels count as defaults", () => {
  assert.equal(isDefaultPaneName("Grok", 0), true);
  assert.equal(isDefaultPaneName("Grok panel 2", 1), true);
  assert.equal(isDefaultPaneName("Larry", 0), true);
  assert.equal(isDefaultPaneName("Larry (the asparagus)", 0), true);
  assert.equal(isDefaultPaneName("Larry (the asparagus) 2", 1), true);
  assert.equal(isDefaultPaneName("Junior", 0), true);
  assert.equal(isDefaultPaneName("Junior", 3), true);
  assert.equal(isDefaultPaneName("Study buddy", 0), false);
});

test("status lines use the pane name", () => {
  assert.equal(chatStatusLine("Junior", "working"), "Junior is working…");
  assert.equal(chatStatusLine("Junior", "thinking"), "Junior is thinking…");
  assert.equal(chatStatusLine("Junior", "writing"), "Junior is writing…");
  assert.equal(chatStatusLine("Junior", "generating"), "Junior is generating…");
});
