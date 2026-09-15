import assert from "node:assert/strict";
import test from "node:test";
import {
  dedupeArticlesById,
  listNextPageOffset,
  listRemovesOnRead,
  listShowsUnreadOnly,
  nextDistinctArticle,
  prevDistinctArticle,
  shelfSupportsUnreadFilter,
} from "./list-navigation";
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
  assert.equal(listShowsUnreadOnly(feed, true), true);
  assert.equal(listRemovesOnRead(feed), true);
});

test("inbox unread filter does not remove rows on read", () => {
  assert.equal(listShowsUnreadOnly({ kind: "inbox" }, true), true);
  assert.equal(listRemovesOnRead({ kind: "inbox" }), false);
});

test("shelfSupportsUnreadFilter includes Fox feeds", () => {
  assert.equal(shelfSupportsUnreadFilter({ kind: "inbox" }), true);
  assert.equal(shelfSupportsUnreadFilter({ kind: "category", id: "x" }), true);
  assert.equal(shelfSupportsUnreadFilter({ kind: "feed", id: "fox" }), true);
});

test("dedupeArticlesById keeps first title per id", () => {
  const rows = dedupeArticlesById([row("a"), row("a"), row("b"), row("a")]);
  assert.deepEqual(
    rows.map((item) => item.id),
    ["a", "b"],
  );
});

test("nextDistinctArticle never returns the same id or wraps", () => {
  const list = [row("a"), row("b"), row("c")];
  assert.equal(nextDistinctArticle(list, "a")?.id, "b");
  assert.equal(nextDistinctArticle(list, "b")?.id, "c");
  assert.equal(nextDistinctArticle(list, "c"), null);
  assert.equal(nextDistinctArticle([row("b"), row("c")], "a")?.id, "b");
  assert.equal(nextDistinctArticle([row("a"), row("a"), row("b")], "a")?.id, "b");
});

test("five Next clicks after splice yield five different ids", () => {
  let list = [row("a"), row("b"), row("c"), row("d"), row("e"), row("f")];
  let current: string | null = "a";
  const seen: string[] = [];
  for (let step = 0; step < 5; step += 1) {
    list = list.filter((item) => item.id !== current);
    const next = nextDistinctArticle(list, current);
    assert.ok(next, `step ${step} should advance`);
    assert.notEqual(next.id, current);
    assert.equal(seen.includes(next.id), false);
    seen.push(next.id);
    current = next.id;
  }
  assert.deepEqual(seen, ["b", "c", "d", "e", "f"]);
});

test("prevDistinctArticle does not wrap to the last row", () => {
  assert.equal(prevDistinctArticle([row("a"), row("b")], "a"), null);
  assert.equal(prevDistinctArticle([row("a"), row("b")], "b")?.id, "a");
});

test("unread API offset follows visible length after splices; Fox all uses fetched count", () => {
  assert.equal(listNextPageOffset({ unreadApi: true, visibleCount: 35, fetchedCount: 40 }), 35);
  assert.equal(listNextPageOffset({ unreadApi: false, visibleCount: 35, fetchedCount: 40 }), 40);
  assert.equal(listNextPageOffset({ unreadApi: false, visibleCount: 40, fetchedCount: 40 }), 40);
});
