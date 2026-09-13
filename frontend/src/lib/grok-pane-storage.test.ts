import assert from "node:assert/strict";
import test from "node:test";
import { labelFromPreferences, labelsFromPanes, mergePreferenceLabels, scrubDefaultPaneLabels } from "@/lib/grok-pane-storage";
import { createGrokPane, defaultGrokPaneName } from "@/components/grok-pane";
import { DEFAULT_PANE_NAME } from "@/lib/grok-pane-name";

test("the default pane name is Larry, not Grok", () => {
  assert.equal(DEFAULT_PANE_NAME, "Larry (the asparagus)");
  assert.equal(defaultGrokPaneName(0), "Larry (the asparagus)");
  assert.equal(defaultGrokPaneName(1), "Larry (the asparagus) 2");
  assert.equal(createGrokPane(0).displayName, "Larry (the asparagus)");
});

test("labelFromPreferences reads by pane index", () => {
  const labels = { "0": "Larry (the asparagus)", "1": "Junior" };
  assert.equal(labelFromPreferences(labels, 0, DEFAULT_PANE_NAME), "Larry (the asparagus)");
  assert.equal(labelFromPreferences(labels, 1, defaultGrokPaneName(1)), "Junior");
  assert.equal(labelFromPreferences(labels, 2, defaultGrokPaneName(2)), defaultGrokPaneName(2));
});

test("mergePreferenceLabels applies index keys", () => {
  const panes = [createGrokPane(0), createGrokPane(1)];
  const merged = mergePreferenceLabels(panes, { "1": "Junior" });
  assert.equal(merged[0]!.displayName, DEFAULT_PANE_NAME);
  assert.equal(merged[1]!.displayName, "Junior");
});

test("labelsFromPanes exports index map", () => {
  const panes = [{ ...createGrokPane(0), displayName: "Big Larry" }];
  assert.deepEqual(labelsFromPanes(panes), { "0": "Big Larry" });
});

test("labelsFromPanes skips the default label", () => {
  const panes = [createGrokPane(0)];
  assert.deepEqual(labelsFromPanes(panes), {});
});

test("mergePreferenceLabels keeps a custom local name over a default preference", () => {
  const panes = [{ ...createGrokPane(0), displayName: "Big Larry" }];
  const merged = mergePreferenceLabels(panes, { "0": DEFAULT_PANE_NAME });
  assert.equal(merged[0]!.displayName, "Big Larry");
});

test("a stored legacy Grok label does not override the Larry default", () => {
  const panes = [createGrokPane(0), createGrokPane(1)];
  const merged = mergePreferenceLabels(panes, { "0": "Grok", "1": "Grok panel 2" });
  assert.equal(merged[0]!.displayName, DEFAULT_PANE_NAME);
  assert.equal(merged[1]!.displayName, defaultGrokPaneName(1));
});

test("scrubDefaultPaneLabels drops both current and legacy default labels", () => {
  const scrubbed = scrubDefaultPaneLabels({
    "0": "Grok",
    "1": "Grok panel 2",
    "2": defaultGrokPaneName(2),
    "3": "Larry the second",
  });
  assert.deepEqual(scrubbed, { "3": "Larry the second" });
});
