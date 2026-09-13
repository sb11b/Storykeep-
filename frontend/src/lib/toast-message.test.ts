import assert from "node:assert/strict";
import test from "node:test";
import { ApiError } from "@/lib/api";
import { actionErrorMessage } from "@/lib/toast-message";

test("actionErrorMessage includes HTTP code and server message", () => {
  const text = actionErrorMessage(new ApiError(404, "Conversation not found."), "delete chat", "Could not delete that chat");
  assert.match(text, /Could not delete chat \(HTTP 404\): Conversation not found\./);
});

test("actionErrorMessage never returns an empty tail", () => {
  const text = actionErrorMessage(new Error(""), "delete chat", "Could not delete that chat");
  assert.match(text, /Could not delete chat \(HTTP error\): .+/);
});
