import assert from "node:assert/strict";
import test from "node:test";
import {
  isFeedId,
  isNoteShrinkMessage,
  parseErrorPayload,
  restoreCharsConfirm,
  shrinkConfirmMessage,
} from "@/lib/api-errors";

test("parseErrorPayload maps feed UUID dumps to Invalid feed", () => {
  assert.equal(
    parseErrorPayload({
      detail: [
        {
          type: "uuid_parsing",
          loc: ["path", "feed_id"],
          msg: "Input should be a valid UUID, invalid character: expected an optional prefix of `urn:uuid:` followed by [0-9a-fA-F-], found `r` at 1",
          input: "refresh",
        },
      ],
    }),
    "Invalid feed",
  );
  assert.equal(
    parseErrorPayload({
      detail: "Input should be a valid UUID, invalid character: found `r` at 1",
    }),
    "Invalid feed",
  );
});

test("isFeedId accepts list-API UUIDs only", () => {
  assert.equal(isFeedId("2f2fae2a-22f3-483b-a4ae-8d49c40f1e9c"), true);
  assert.equal(isFeedId("refresh"), false);
  assert.equal(isFeedId("https://example.com/rss"), false);
  assert.equal(isFeedId(""), false);
});

test("parseErrorPayload maps conversation UUID dumps to Invalid chat", () => {
  assert.equal(
    parseErrorPayload({
      detail: [
        {
          type: "uuid_parsing",
          loc: ["path", "conversation_id"],
          msg: "Input should be a valid UUID, invalid character: expected an optional prefix of `urn:uuid:` followed by [0-9a-fA-F-], found `n` at 1",
          input: "new",
        },
      ],
    }),
    "Invalid chat",
  );
});

test("parseErrorPayload reads nested FastAPI detail.message", () => {
  const message = shrinkConfirmMessage(15000, 239);
  assert.equal(
    parseErrorPayload({
      detail: { code: "note_shrink", message, current_chars: 15000, incoming_chars: 239 },
    }),
    message,
  );
});

test("shrink confirm copy matches the composer prompt", () => {
  assert.equal(shrinkConfirmMessage(15000, 239), "This save is much shorter (239 vs 15000). Save anyway?");
  assert.equal(restoreCharsConfirm(15000), "Restore 15000 characters?");
  assert.equal(isNoteShrinkMessage("This save is much shorter (239 vs 15000). Save anyway?"), true);
});
