import assert from "node:assert/strict";
import test from "node:test";
import {
  GROK_REPLY_SELECTOR,
  grokReplySpeechScript,
  readRenderedReplyText,
  replyBodySelector,
} from "@/lib/grok-reply-speech";

function fakeBody(innerText: string, textContent = ""): HTMLElement {
  return {
    innerText,
    textContent,
    querySelectorAll: () => [],
  } as unknown as HTMLElement;
}

test("grokReplySpeechScript reads innerText from the rendered reply body", () => {
  const result = grokReplySpeechScript(fakeBody("Hello! How can I help with your code?"), "markdown ignored");
  assert.equal(result.script, "Hello! How can I help with your code?");
  assert.equal(result.source, "innerText");
  assert.equal(result.selector, GROK_REPLY_SELECTOR);
});

test("grokReplySpeechScript collapses whitespace from a long reply", () => {
  const result = grokReplySpeechScript(fakeBody("First line.\n\n  Second   line.\n"));
  assert.equal(result.script, "First line. Second line.");
  assert.ok(result.script.length > 0);
});

test("grokReplySpeechScript uses textContent when innerText is unavailable", () => {
  const result = grokReplySpeechScript(fakeBody("", "Fallback body text"));
  assert.equal(result.script, "Fallback body text");
  assert.equal(result.source, "innerText");
});

test("grokReplySpeechScript falls back to markdown when the body is unmounted", () => {
  const result = grokReplySpeechScript(null, "Hello from Larry");
  assert.equal(result.script, "Hello from Larry");
  assert.equal(result.source, "markdown");
  assert.equal(result.visibleWordCount, 3);
});

test("grokReplySpeechScript reports empty only when there is truly no text", () => {
  const result = grokReplySpeechScript(fakeBody("   "), "   ");
  assert.equal(result.script, "");
  assert.equal(result.source, "empty");
});

test("replyBodySelector targets one reply body by message id", () => {
  assert.equal(replyBodySelector("abc-123"), 'div.note-md[data-grok-reply-body="abc-123"]');
});

function withDocument(match: HTMLElement | null, run: () => void) {
  const previous = (globalThis as { document?: unknown }).document;
  (globalThis as { document?: unknown }).document = { querySelector: () => match };
  try {
    run();
  } finally {
    (globalThis as { document?: unknown }).document = previous;
  }
}

test("readRenderedReplyText returns trimmed innerText from the document", () => {
  withDocument(fakeBody("  Hello Steve, here is the fix.  "), () => {
    const result = readRenderedReplyText("abc-123");
    assert.equal(result.text, "Hello Steve, here is the fix.");
    assert.equal(result.found, true);
    assert.equal(result.selector, replyBodySelector("abc-123"));
  });
});

test("readRenderedReplyText reports a selector miss when nothing matches", () => {
  withDocument(null, () => {
    const result = readRenderedReplyText("abc-123");
    assert.equal(result.text, "");
    assert.equal(result.found, false);
  });
});
