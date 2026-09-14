import assert from "node:assert/strict";
import test from "node:test";
import {
  labelFromPreferences,
  labelsFromPanes,
  loadSavedGrokPanes,
  mergePreferenceLabels,
  sanitizePendingAttachments,
  saveGrokPanes,
  scrubDefaultPaneLabels,
} from "@/lib/grok-pane-storage";
import { createGrokPane, defaultGrokPaneName } from "@/components/grok-pane";
import { DEFAULT_PANE_NAME } from "@/lib/grok-pane-name";

test("pane storage keeps pending attach ids and conversation id across reload", () => {
  const mediaId = "11111111-1111-1111-1111-111111111111";
  const conversationId = "22222222-2222-2222-2222-222222222222";
  const store: Record<string, string> = {};
  const localStorage = {
    getItem: (key: string) => store[key] ?? null,
    setItem: (key: string, value: string) => {
      store[key] = value;
    },
  };
  const originalWindow = globalThis.window;
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: { localStorage },
  });
  try {
    const panes = [
      {
        ...createGrokPane(0),
        conversationId,
        pendingAttachments: [
          {
            id: mediaId,
            name: "notes.pdf",
            size: 12,
            url: `blob:http://localhost/${mediaId}`,
            kind: "file" as const,
            content_type: "application/pdf",
          },
        ],
      },
    ];
    saveGrokPanes(panes);
    const loaded = loadSavedGrokPanes();
    assert.equal(loaded?.[0]?.conversationId, conversationId);
    assert.equal(loaded?.[0]?.pendingAttachments[0]?.id, mediaId);
    assert.equal(loaded?.[0]?.pendingAttachments[0]?.url, `/api/v1/media/${mediaId}`);
    assert.deepEqual(sanitizePendingAttachments([{ id: "not-a-uuid", name: "x" }]), []);
  } finally {
    Object.defineProperty(globalThis, "window", { configurable: true, value: originalWindow });
  }
});

test("the default pane name is Junior, not Larry or Grok", () => {
  assert.equal(DEFAULT_PANE_NAME, "Junior");
  assert.equal(defaultGrokPaneName(0), "Junior");
  assert.equal(defaultGrokPaneName(1), "Junior 2");
  assert.equal(createGrokPane(0).displayName, "Junior");
});

test("labelFromPreferences reads by pane index", () => {
  const labels = { "0": "Junior", "1": "Study buddy" };
  assert.equal(labelFromPreferences(labels, 0, DEFAULT_PANE_NAME), "Junior");
  assert.equal(labelFromPreferences(labels, 1, defaultGrokPaneName(1)), "Study buddy");
  assert.equal(labelFromPreferences(labels, 2, defaultGrokPaneName(2)), defaultGrokPaneName(2));
});

test("mergePreferenceLabels applies index keys", () => {
  const panes = [createGrokPane(0), createGrokPane(1)];
  const merged = mergePreferenceLabels(panes, { "1": "Study buddy" });
  assert.equal(merged[0]!.displayName, DEFAULT_PANE_NAME);
  assert.equal(merged[1]!.displayName, "Study buddy");
});

test("labelsFromPanes exports index map", () => {
  const panes = [{ ...createGrokPane(0), displayName: "Study buddy" }];
  assert.deepEqual(labelsFromPanes(panes), { "0": "Study buddy" });
});

test("labelsFromPanes skips the default label", () => {
  const panes = [createGrokPane(0)];
  assert.deepEqual(labelsFromPanes(panes), {});
});

test("mergePreferenceLabels keeps a custom local name over a default preference", () => {
  const panes = [{ ...createGrokPane(0), displayName: "Study buddy" }];
  const merged = mergePreferenceLabels(panes, { "0": DEFAULT_PANE_NAME });
  assert.equal(merged[0]!.displayName, "Study buddy");
});

test("a stored legacy Grok or Larry label does not override the Junior default", () => {
  const panes = [createGrokPane(0), createGrokPane(1)];
  const merged = mergePreferenceLabels(panes, { "0": "Grok", "1": "Larry (the asparagus) 2" });
  assert.equal(merged[0]!.displayName, DEFAULT_PANE_NAME);
  assert.equal(merged[1]!.displayName, defaultGrokPaneName(1));
});

test("scrubDefaultPaneLabels drops current and legacy default labels", () => {
  const scrubbed = scrubDefaultPaneLabels({
    "0": "Grok",
    "1": "Grok panel 2",
    "2": "Larry (the asparagus)",
    "3": "Junior",
    "4": "Larry the second",
  });
  assert.deepEqual(scrubbed, { "4": "Larry the second" });
});
