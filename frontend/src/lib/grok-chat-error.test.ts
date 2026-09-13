import assert from "node:assert/strict";
import test from "node:test";
import { formatChatError, withAssistantName } from "./grok-chat-error";

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

test("formatChatError shows the pane name instead of the upstream model name", () => {
  assert.equal(
    formatChatError(504, "Grok timed out after 90s.", "Junior"),
    "Chat failed (HTTP 504): Junior timed out after 90s.",
  );
  assert.equal(
    formatChatError(504, "Larry timed out after 90s.", "Junior"),
    "Chat failed (HTTP 504): Junior timed out after 90s.",
  );
});

test("withAssistantName leaves a message alone when there is no pane name", () => {
  assert.equal(withAssistantName("Grok timed out."), "Grok timed out.");
  assert.equal(withAssistantName("Grokking is fine", "Junior"), "Grokking is fine");
});
