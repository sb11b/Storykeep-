import assert from "node:assert/strict";
import test from "node:test";
import { ApiError } from "@/lib/api";
import {
  BUILD_WORD_FAIL,
  EMPTY_WORD_BODY,
  FORBIDDEN_WORD,
  filenameFromContentDisposition,
  isPersistedMessageId,
  replyFileStem,
  replyCopyText,
  replyHasWordBody,
  wordDownloadToast,
} from "@/lib/chat-message-docx";

test("Word download uses a persisted message id", () => {
  assert.equal(isPersistedMessageId("2f1a0c6e-4b3d-4a1f-9c8e-7d6b5a4c3b2a"), true);
  assert.equal(isPersistedMessageId("local"), false);
});

test("Content-Disposition filename is read for the .docx save-as name", () => {
  assert.equal(
    filenameFromContentDisposition('attachment; filename="DAT-200 grammar.docx"'),
    "DAT-200 grammar.docx",
  );
});

test("Markdown and text saves use the DAT heading", () => {
  assert.equal(replyFileStem("# Grammar-fixed DAT-200 paper\n\nBody"), "Grammar-fixed DAT-200 paper");
  assert.equal(replyFileStem("Just a line\n\nMore."), "Just a line");
});

test("Copy and Word drop keep/notes footers", () => {
  assert.equal(
    replyCopyText("The slope is two.\n\nUse Add to notes if you want this kept."),
    "The slope is two.",
  );
  assert.equal(
    replyCopyText("The slope is two. If you want this kept, use Add to notes."),
    "The slope is two.",
  );
  assert.equal(replyCopyText("The slope is two."), "The slope is two.");
  assert.equal(
    replyCopyText("The slope is two.\n\n*Use Add to notes if you want this kept.*"),
    "The slope is two.",
  );
});

test("empty and tool-only replies have no Word body", () => {
  assert.equal(replyHasWordBody(""), false);
  assert.equal(replyHasWordBody("   "), false);
  assert.equal(replyHasWordBody("![](/api/v1/media/abc)"), false);
  assert.equal(replyHasWordBody("```json\n{\"tool\":\"code_interpreter\"}\n```"), false);
  assert.equal(replyHasWordBody("# Grammar-fixed DAT-200 paper\n\nBody"), true);
});

test("Word toasts distinguish build vs 403 vs empty body", () => {
  assert.equal(wordDownloadToast(new ApiError(403, "Chat history is not stored for demo accounts.")), "Chat history is not stored for demo accounts.");
  assert.equal(wordDownloadToast(new ApiError(403, "")), FORBIDDEN_WORD);
  assert.equal(wordDownloadToast(new ApiError(400, EMPTY_WORD_BODY)), EMPTY_WORD_BODY);
  assert.equal(wordDownloadToast(new ApiError(400, BUILD_WORD_FAIL)), BUILD_WORD_FAIL);
  assert.equal(wordDownloadToast(new ApiError(502, "broken zip")), BUILD_WORD_FAIL);
});
