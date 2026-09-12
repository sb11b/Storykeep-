import assert from "node:assert/strict";
import test from "node:test";
import { listRemovesOnRead, listShowsUnreadOnly, pickAdvanceTarget, shelfSupportsUnreadFilter } from "./list-navigation";
import type { ArticleListItem } from "./types";

const row = (id: string): ArticleListItem =>
  ({
    id,
    title: id,
    url: "https://example.com",
    is_read: false,
  }) as ArticleListItem;

test("listRemovesOnRead for unread and feed queues only", () => {
  assert.equal(listRemovesOnRead({ kind: "unread" }), true);
  assert.equal(listRemovesOnRead({ kind: "feed", id: "fox" }), true);
  assert.equal(listRemovesOnRead({ kind: "inbox" }), false);
  assert.equal(listRemovesOnRead({ kind: "saved" }), false);
  assert.equal(listRemovesOnRead({ kind: "starred" }), false);
  assert.equal(listRemovesOnRead({ kind: "category", id: "news" }), false);
  assert.equal(listRemovesOnRead({ kind: "schoolwork" }), false);
  assert.equal(listRemovesOnRead({ kind: "vault" }), false);
});

test("feed lists remove on read without unread-only API filter", () => {
  const feed = { kind: "feed" as const, id: "feed-1" };
  assert.equal(listShowsUnreadOnly(feed, false), false);
  assert.equal(listRemovesOnRead(feed), true);
});

test("inbox unread filter does not remove rows on read", () => {
  assert.equal(listShowsUnreadOnly({ kind: "inbox" }, true), true);
  assert.equal(listRemovesOnRead({ kind: "inbox" }), false);
});

test("pickAdvanceTarget returns the next visible row after removal", () => {
  assert.equal(pickAdvanceTarget([row("b"), row("c")], 0, true)?.id, "b");
  assert.equal(pickAdvanceTarget([row("a"), row("b"), row("c")], 0, false)?.id, "b");
  assert.equal(pickAdvanceTarget([row("a"), row("b")], 2, true), null);
});

test("shelfSupportsUnreadFilter covers inbox and category only", () => {
  assert.equal(shelfSupportsUnreadFilter({ kind: "inbox" }), true);
  assert.equal(shelfSupportsUnreadFilter({ kind: "category", id: "x" }), true);
  assert.equal(shelfSupportsUnreadFilter({ kind: "feed", id: "x" }), false);
});
