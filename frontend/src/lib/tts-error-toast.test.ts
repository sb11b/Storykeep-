import assert from "node:assert/strict";
import test from "node:test";
import { ApiError } from "@/lib/api";
import { ttsErrorMessage } from "@/lib/tts-error-toast";

test("ttsErrorMessage includes HTTP code and server message", () => {
  const text = ttsErrorMessage(new ApiError(401, "xAI rejected the API key."));
  assert.match(text, /Could not read \(HTTP 401\): xAI rejected the API key\./);
});

test("ttsErrorMessage never returns an empty tail", () => {
  const text = ttsErrorMessage(new Error(""));
  assert.match(text, /Could not read \(HTTP error\): .+/);
});
