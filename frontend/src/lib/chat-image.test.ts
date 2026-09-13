import assert from "node:assert/strict";
import test from "node:test";
import { CLARIFY_EDIT_OR_GENERATE, collectImageMediaIds, imageToolIntent } from "./chat-image";

test("make me look older with a selfie is edit", () => {
  assert.equal(imageToolIntent("Make me look older", true), "edit");
  assert.equal(imageToolIntent("age this picture", true), "edit");
  assert.equal(imageToolIntent("make it look older", true), "edit");
});

test("make this look older without a selfie asks once", () => {
  assert.equal(imageToolIntent("make me look older", false), "clarify");
  assert.equal(imageToolIntent("make this look older", false), "clarify");
  assert.equal(imageToolIntent("make it older", false), "clarify");
  assert.equal(
    CLARIFY_EDIT_OR_GENERATE,
    "Generate a new older-looking picture, or attach one to edit?",
  );
});

test("photo talk stays chat", () => {
  assert.equal(imageToolIntent("Tell me about photo metadata", false), null);
  assert.equal(imageToolIntent("what is a picture element in HTML", false), null);
  assert.equal(imageToolIntent("older python versions", false), null);
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

test("collectImageMediaIds prefers the pending chip then the last user photo", () => {
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
    ["selfie"],
  );
});
