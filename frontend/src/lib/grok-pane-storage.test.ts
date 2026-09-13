import assert from "node:assert/strict";
import test from "node:test";
import { labelFromPreferences, labelsFromPanes, mergePreferenceLabels } from "@/lib/grok-pane-storage";
import { createGrokPane, defaultGrokPaneName } from "@/components/grok-pane";

test("labelFromPreferences reads by pane index", () => {
  const labels = { "0": "Larry (the asparagus)", "1": "Junior" };
  assert.equal(labelFromPreferences(labels, 0, "Grok"), "Larry (the asparagus)");
  assert.equal(labelFromPreferences(labels, 1, "Grok panel 2"), "Junior");
  assert.equal(labelFromPreferences(labels, 2, "Grok panel 3"), "Grok panel 3");
});

test("mergePreferenceLabels applies index keys", () => {
  const panes = [createGrokPane(0), createGrokPane(1)];
  const merged = mergePreferenceLabels(panes, { "0": "Larry (the asparagus)" });
  assert.equal(merged[0]!.displayName, "Larry (the asparagus)");
  assert.equal(merged[1]!.displayName, defaultGrokPaneName(1));
});

test("labelsFromPanes exports index map", () => {
  const panes = [{ ...createGrokPane(0), displayName: "Larry (the asparagus)" }];
  assert.deepEqual(labelsFromPanes(panes), { "0": "Larry (the asparagus)" });
});
