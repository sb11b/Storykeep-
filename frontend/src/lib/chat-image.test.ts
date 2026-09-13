import assert from "node:assert/strict";
import test from "node:test";
import { collectImageMediaIds, imageToolIntent } from "./chat-image";

test("make me look older with a selfie is edit", () => {
  assert.equal(imageToolIntent("Make me look older", true), "edit");
  assert.equal(imageToolIntent("age this picture", true), "edit");
});

test("what's in this photo is vision only", () => {
  assert.equal(imageToolIntent("what's in this picture?", true), null);
  assert.equal(imageToolIntent("describe this selfie", true), null);
});

test("generate without a photo is generate", () => {
  assert.equal(imageToolIntent("generate an image of a red notebook", false), "generate");
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
