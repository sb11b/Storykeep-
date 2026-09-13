import assert from "node:assert/strict";
import test from "node:test";
import {
  readReplyText,
  replyBodyFromTrigger,
  REPLY_BODY_SELECTOR,
  REPLY_ROW_SELECTOR,
} from "@/lib/grok-reply-speech";

function fakeEl(innerText: string, className = "note-md markdown", textContent = ""): HTMLElement {
  return { innerText, className, textContent } as unknown as HTMLElement;
}

/** Stand-in for a Listen button sitting inside a reply row. */
function fakeTrigger(row: { body: HTMLElement | null; matches?: string } | null): HTMLElement {
  const rowEl = row
    ? ({
        className: "chat-message larry-reply",
        innerText: "LARRY (THE ASPARAGUS) REPLIED Hello Steve. Listen Copy",
        querySelector: (selector: string) => (selector === REPLY_BODY_SELECTOR ? row.body : null),
      } as unknown as HTMLElement)
    : null;
  return {
    closest: (selector: string) => (selector === REPLY_ROW_SELECTOR ? rowEl : null),
  } as unknown as HTMLElement;
}

test("replyBodyFromTrigger walks up to the row and down to the body", () => {
  const body = fakeEl("Hello Steve.");
  assert.equal(replyBodyFromTrigger(fakeTrigger({ body })), body);
});

test("replyBodyFromTrigger falls back to the row when it has no marked body", () => {
  const found = replyBodyFromTrigger(fakeTrigger({ body: null }));
  assert.equal(found?.className, "chat-message larry-reply");
});

test("replyBodyFromTrigger returns null without a row to climb to", () => {
  assert.equal(replyBodyFromTrigger(fakeTrigger(null)), null);
  assert.equal(replyBodyFromTrigger(null), null);
});

test("readReplyText reads innerText from the button's own reply row", () => {
  const resolved = readReplyText({
    trigger: fakeTrigger({ body: fakeEl("  Hello Steve, here is the fix.  ") }),
    markdown: "ignored",
  });
  assert.equal(resolved.text, "Hello Steve, here is the fix.");
  assert.equal(resolved.chars, 29);
  assert.equal(resolved.source, "row");
  assert.equal(resolved.className, "note-md markdown");
});

test("readReplyText uses the registered body when there is no trigger", () => {
  const resolved = readReplyText({ body: fakeEl("Sticky bar reply.") });
  assert.equal(resolved.text, "Sticky bar reply.");
  assert.equal(resolved.source, "body");
});

test("readReplyText falls back to markdown, stripped of syntax", () => {
  const resolved = readReplyText({ markdown: "## Heading\n\nHello **Steve**." });
  assert.equal(resolved.source, "markdown");
  assert.ok(resolved.chars > 0);
  assert.ok(resolved.text.includes("Hello"));
});

test("readReplyText reports empty only when nothing has any text", () => {
  const resolved = readReplyText({
    trigger: fakeTrigger({ body: fakeEl("   ") }),
    body: fakeEl("  "),
    markdown: "   ",
  });
  assert.equal(resolved.text, "");
  assert.equal(resolved.chars, 0);
  assert.equal(resolved.source, "empty");
});

test("readReplyText uses textContent when innerText is unavailable", () => {
  const resolved = readReplyText({ body: fakeEl("", "note-md", "From textContent") });
  assert.equal(resolved.text, "From textContent");
});
