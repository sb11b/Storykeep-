import assert from "node:assert/strict";
import test from "node:test";
import { filenameFromContentDisposition, isPersistedMessageId, replyFileStem } from "@/lib/chat-message-docx";

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
});
