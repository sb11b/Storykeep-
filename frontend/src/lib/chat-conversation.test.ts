import assert from "node:assert/strict";
import test from "node:test";
import {
  CHAT_CREATE_TIMEOUT_TOAST,
  INVALID_CHAT_TOAST,
  chatCreateErrorToast,
  conversationIdForRequest,
  isConversationId,
  isReservedConversationPath,
} from "./chat-conversation";

test("isConversationId accepts UUIDs only", () => {
  assert.equal(isConversationId("2f2fae2a-22f3-483b-a4ae-8d49c40f1e9c"), true);
  assert.equal(isConversationId("new"), false);
  assert.equal(isConversationId("refresh"), false);
  assert.equal(isConversationId("Hello"), false);
  assert.equal(isConversationId(""), false);
  assert.equal(isConversationId(null), false);
});

test("reserved conversation path words are never UUIDs", () => {
  assert.equal(isReservedConversationPath("new"), true);
  assert.equal(isReservedConversationPath("refresh"), true);
  assert.equal(isReservedConversationPath("  NEW "), true);
  assert.equal(conversationIdForRequest("new"), null);
  assert.equal(conversationIdForRequest("refresh"), null);
  assert.equal(conversationIdForRequest("2f2fae2a-22f3-483b-a4ae-8d49c40f1e9c"), "2f2fae2a-22f3-483b-a4ae-8d49c40f1e9c");
});

test("create 504 maps to retry toast, not a raw nginx page", () => {
  assert.equal(chatCreateErrorToast(504, CHAT_CREATE_TIMEOUT_TOAST), CHAT_CREATE_TIMEOUT_TOAST);
  assert.equal(chatCreateErrorToast(504, "Chat create timed out — retry"), CHAT_CREATE_TIMEOUT_TOAST);
  assert.equal(chatCreateErrorToast(504, "Gateway Timeout"), null);
  assert.equal(chatCreateErrorToast(504, "Chat failed (HTTP 504): xAI silent"), null);
});

test("422 UUID maps to Invalid chat", () => {
  assert.equal(chatCreateErrorToast(422, INVALID_CHAT_TOAST), INVALID_CHAT_TOAST);
  assert.equal(
    chatCreateErrorToast(422, "Input should be a valid UUID, invalid character: found `n` at 1"),
    INVALID_CHAT_TOAST,
  );
  assert.equal(chatCreateErrorToast(400, "Invalid chat"), INVALID_CHAT_TOAST);
});
