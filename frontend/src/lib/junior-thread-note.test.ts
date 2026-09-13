import assert from "node:assert/strict";
import test from "node:test";
import { saveableThreadTurns, threadNoteMarkdown, threadNoteTitle } from "./junior-thread-note";

test("threadNoteTitle prefers a renamed thread", () => {
  assert.equal(
    threadNoteTitle({ conversationTitle: "Transfer block recap", firstUserLine: "hello" }),
    "Transfer block recap",
  );
});

test("threadNoteTitle uses the first user line when the thread is still New chat", () => {
  assert.equal(
    threadNoteTitle({ conversationTitle: "New chat", firstUserLine: "Explain the chain rule" }),
    "Explain the chain rule",
  );
});

test("threadNoteTitle falls back to Junior chat plus the date", () => {
  assert.equal(
    threadNoteTitle({ conversationTitle: "", firstUserLine: "  ", now: new Date(2026, 8, 13) }),
    "Junior chat 2026-09-13",
  );
});

test("threadNoteMarkdown keeps every turn and fenced code", () => {
  const markdown = threadNoteMarkdown(
    [
      { role: "user", content: "What is GDP?" },
      { role: "assistant", content: "Gross domestic product.\n\n```js\nconst n = 1;\n```" },
      { role: "user", content: "Give an example." },
      { role: "assistant", content: "US output in a year." },
    ],
    { title: "GDP thread" },
  );
  assert.match(markdown, /^# GDP thread\n/);
  assert.match(markdown, /\*\*Steve\*\*\n\nWhat is GDP\?/);
  assert.match(markdown, /\*\*Junior\*\*\n\nGross domestic product/);
  assert.match(markdown, /```js\nconst n = 1;\n```/);
  assert.match(markdown, /\*\*Steve\*\*\n\nGive an example\./);
  assert.equal(markdown.includes("US output in a year."), true);
});

test("saveableThreadTurns drops empty waiting lines", () => {
  const kept = saveableThreadTurns([
    { role: "user", content: "Hi" },
    { role: "assistant", content: "   " },
    { role: "assistant", content: "Hello." },
  ]);
  assert.equal(kept.length, 2);
  assert.equal(kept[1]?.content, "Hello.");
});
