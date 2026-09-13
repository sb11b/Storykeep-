import assert from "node:assert/strict";
import test from "node:test";
import { collectImageMediaIds, imageToolIntent, thisTurnImageMediaIds } from "./chat-image";

test("make me look older with a selfie is edit", () => {
  assert.equal(imageToolIntent("Make me look older", true), "edit");
  assert.equal(imageToolIntent("age this picture", true), "edit");
  assert.equal(imageToolIntent("make it look older", true), "edit");
});

test("bald with a selfie is edit", () => {
  assert.equal(imageToolIntent("let me see me bald", true), "edit");
  assert.equal(imageToolIntent("make me bald", true), "edit");
  assert.equal(imageToolIntent("bald", true), "edit");
});

test("edit phrases without this-turn photo stay text", () => {
  assert.equal(imageToolIntent("make me look older", false), null);
  assert.equal(imageToolIntent("make this look older", false), null);
  assert.equal(imageToolIntent("make it older", false), null);
  assert.equal(imageToolIntent("let me see me bald", false), null);
});

test("photo talk stays chat", () => {
  assert.equal(imageToolIntent("Tell me about photo metadata", false), null);
  assert.equal(imageToolIntent("what is a picture element in HTML", false), null);
  assert.equal(imageToolIntent("older python versions", false), null);
});

test("chat reliability questions are not Imagine", () => {
  assert.equal(imageToolIntent("what should I expect from chat reliability?", false), null);
  assert.equal(imageToolIntent("what should I expect from chat reliability?", true), null);
  const spec = [
    "Junior image-gate is firing on every message that quotes the spec",
    '("make me look older", "image path").',
    "Verify: keep partials on 60s.",
  ].join("\n");
  assert.equal(imageToolIntent(spec, false), null);
  assert.equal(imageToolIntent(spec, true), null);
  assert.equal(imageToolIntent('Tell me what to expect. Example: "make me look older".', false), null);
});

test("pasted ticket about Imagine is text even with a prior photo flag", () => {
  const ticket = [
    "Okay the image problem is not solved. Here is the newest problem.",
    "Paste a ticket containing make me look older.",
    "Verify: text only, no image prompt.",
    "- checklist item: make me look older",
  ].join("\n");
  assert.equal(imageToolIntent(ticket, false), null);
  assert.equal(imageToolIntent(ticket, true), null);
});

test("what's in this photo is vision only", () => {
  assert.equal(imageToolIntent("what's in this picture?", true), null);
  assert.equal(imageToolIntent("describe this selfie", true), null);
});

test("generate without a photo is generate", () => {
  assert.equal(imageToolIntent("generate an image of a red notebook", false), "generate");
  assert.equal(imageToolIntent("Generate a red notebook", false), "generate");
});

test("recreating an image with a selfie is edit", () => {
  assert.equal(imageToolIntent("recreating an image", true), "edit");
  assert.equal(imageToolIntent("from this photo make me older", true), "edit");
  assert.equal(imageToolIntent("older", true), "edit");
});

test("recreating an image without a selfie is generate", () => {
  assert.equal(imageToolIntent("recreating an image", false), "generate");
});

test("how old and please-look-at stay vision only", () => {
  assert.equal(imageToolIntent("how old is this person", true), null);
  assert.equal(imageToolIntent("Please look at selfie.jpg.", true), null);
});

test("school coding imagine is not image gen", () => {
  assert.equal(imageToolIntent("imagine we have a linked list", false), null);
});

test("this-turn image ids ignore prior thread photos", () => {
  assert.deepEqual(
    thisTurnImageMediaIds([{ id: "pending-1", kind: "image" }]),
    ["pending-1"],
  );
  assert.deepEqual(
    collectImageMediaIds([{ id: "pending-1", kind: "image" }], [
      { role: "user", files: [{ kind: "image", media_id: "old" }] },
    ]),
    ["pending-1"],
  );
  assert.deepEqual(
    collectImageMediaIds([], [
      { role: "user", files: [{ kind: "image", media_id: "selfie" }] },
      { role: "assistant", files: [{ kind: "image", media_id: "generated" }] },
      { role: "user", files: [] },
    ]),
    [],
  );
  assert.deepEqual(
    thisTurnImageMediaIds([{ kind: "image", media_id: "from-message" }]),
    ["from-message"],
  );
});
