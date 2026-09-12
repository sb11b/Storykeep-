import assert from "node:assert/strict";
import test from "node:test";
import { listShowsUnreadOnly, nextRowIndex, pickAdvanceTarget, shelfSupportsUnreadFilter } from "./list-navigation";
import type { ArticleListItem } from "./types";

const row = (id: string): ArticleListItem =>
  ({
    id,
    title: id,
    url: "https://example.com",
    is_read: false,
  }) as ArticleListItem;

test("listShowsUnreadOnly is true for unread shelf", () => {
  assert.equal(listShowsUnreadOnly({ kind: "unread" }, false), true);
});

test("listShowsUnreadOnly respects feed unread filter toggle", () => {
  const feed = { kind: "feed" as const, id: "feed-1" };
  assert.equal(listShowsUnreadOnly(feed, false), false);
  assert.equal(listShowsUnreadOnly(feed, true), true);
});

test("next row stays at index when removing from unread list", () => {
  assert.equal(nextRowIndex(2, true), 2);
  assert.equal(nextRowIndex(2, false), 3);
});

test("pickAdvanceTarget returns the next visible row after removal", () => {
  assert.equal(pickAdvanceTarget([row("b"), row("c")], 0, true)?.id, "b");
  assert.equal(pickAdvanceTarget([row("a"), row("b"), row("c")], 0, false)?.id, "b");
  assert.equal(pickAdvanceTarget([row("a"), row("b")], 2, true), null);
});

test("shelfSupportsUnreadFilter covers inbox feed and category", () => {
  assert.equal(shelfSupportsUnreadFilter({ kind: "inbox" }), true);
  assert.equal(shelfSupportsUnreadFilter({ kind: "feed", id: "x" }), true);
  assert.equal(shelfSupportsUnreadFilter({ kind: "saved" }), false);
});
