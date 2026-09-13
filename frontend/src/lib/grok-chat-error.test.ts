import assert from "node:assert/strict";
import test from "node:test";
import { formatChatError } from "./grok-chat-error";

test("formatChatError includes HTTP status and detail", () => {
  assert.equal(
    formatChatError(504, "Grok timed out after 90s."),
    "Chat failed (HTTP 504): Grok timed out after 90s.",
  );
  assert.equal(
    formatChatError(502, "xAI HTTP 429: rate limit exceeded"),
    "Chat failed (HTTP 502): xAI HTTP 429: rate limit exceeded",
  );
});
