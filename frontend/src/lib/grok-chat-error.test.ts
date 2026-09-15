import assert from "node:assert/strict";
import test from "node:test";
import {
  CHAT_IDLE_TIMEOUT_TOAST,
  chatTimeoutToast,
  formatChatError,
  isOversizedPasteHttp,
  readableXaiToast,
  withAssistantName,
} from "./grok-chat-error";

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

test("readableXaiToast keeps the upstream xAI message", () => {
  assert.equal(
    readableXaiToast("Chat failed (HTTP 502): unknown variant `code_interpreter`"),
    "unknown variant `code_interpreter`",
  );
  assert.equal(readableXaiToast("xAI HTTP 422: invalid tool"), "invalid tool");
  assert.equal(readableXaiToast("rate limit exceeded"), "rate limit exceeded");
});

test("oversized paste HTTP is not a blank 422", () => {
  assert.equal(isOversizedPasteHttp(422, "String should have at most 8000 characters"), true);
  assert.equal(isOversizedPasteHttp(400, "This turn is over the cap. Include a heading, a selection, or the next chunk."), true);
  assert.equal(isOversizedPasteHttp(413, "This turn is over the cap. Include a heading, a selection, or the next chunk."), true);
  assert.equal(isOversizedPasteHttp(422, "unknown variant `code_interpreter`"), false);
});

test("idle timeout toast stays Timed out after 60s", () => {
  assert.equal(
    chatTimeoutToast(504, "Chat failed (HTTP 504): Chat timed out after 60s."),
    CHAT_IDLE_TIMEOUT_TOAST,
  );
  assert.equal(chatTimeoutToast(504, "Timed out after 60s."), CHAT_IDLE_TIMEOUT_TOAST);
  assert.equal(chatTimeoutToast(504, "Chat failed (HTTP 504): xAI silent"), null);
  assert.equal(chatTimeoutToast(502, "Chat timed out after 60s."), null);
});
