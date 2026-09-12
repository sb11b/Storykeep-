"use client";

import { cn } from "@/lib/utils";
import type { Category, Feed } from "@/lib/types";
import type { Shelf } from "@/lib/types";

export function ShelfSwitcher({
  shelf,
  categories,
  groupedFeeds,
  onShelf,
  onAddCategory,
  onAddFeed,
}: {
  shelf: Shelf;
  categories: Category[];
  groupedFeeds: { groups: { category: Category; feeds: Feed[] }[]; uncategorized: Feed[] };
  onShelf: (shelf: Shelf) => void;
  onAddCategory: () => void;
  onAddFeed: () => void;
}) {
  const { groups, uncategorized } = groupedFeeds;
  const hasFeeds = groups.some((group) => group.feeds.length > 0) || uncategorized.length > 0;

  return (
    <div className="px-2 pt-5">
      <p className="pb-2 text-[11px] uppercase tracking-[0.14em] text-sidebar-foreground/50">Shelf switcher</p>
      {!hasFeeds && categories.length === 0 ? (
        <p className="px-0 pb-2 text-xs text-sidebar-foreground/60">No feeds yet. Add a category or feed to begin.</p>
      ) : (
        <div className="space-y-3 pb-2">
          {groups.map(({ category, feeds: groupFeeds }) => (
            <div key={category.id}>
              <button
                type="button"
                onClick={() => onShelf({ kind: "category", id: category.id })}
                className={cn(
                  "w-full rounded-md px-2 py-1 text-left text-sm font-medium transition-colors hover:bg-sidebar-accent/60",
                  shelf.kind === "category" && shelf.id === category.id
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground",
                )}
              >
                {category.name}
              </button>
              {groupFeeds.length ? (
                <ul className="mt-0.5 space-y-0.5 pl-1">
                  {groupFeeds.map((feed) => (
                    <li key={feed.id}>
                      <FeedSwitchRow
                        feed={feed}
                        active={shelf.kind === "feed" && shelf.id === feed.id}
                        onSelect={() => onShelf({ kind: "feed", id: feed.id })}
                      />
                    </li>
                  ))}
                </ul>
              ) : null}
            </div>
          ))}
          {uncategorized.length ? (
            <div>
              <p className="px-2 py-1 text-sm font-medium text-sidebar-foreground">Uncategorized</p>
              <ul className="mt-0.5 space-y-0.5 pl-1">
                {uncategorized.map((feed) => (
                  <li key={feed.id}>
                    <FeedSwitchRow
                      feed={feed}
                      active={shelf.kind === "feed" && shelf.id === feed.id}
                      onSelect={() => onShelf({ kind: "feed", id: feed.id })}
                    />
                  </li>
                ))}
              </ul>
            </div>
          ) : null}
        </div>
      )}
      <div className="flex flex-col gap-1 border-t border-sidebar-border pt-2">
        <button
          type="button"
          onClick={onAddCategory}
          className="rounded-md px-2 py-1.5 text-left text-xs text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
        >
          + Add category
        </button>
        <button
          type="button"
          onClick={onAddFeed}
          className="rounded-md px-2 py-1.5 text-left text-xs text-sidebar-foreground/80 transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
        >
          + Add feed
        </button>
      </div>
    </div>
  );
}

function FeedSwitchRow({
  feed,
  active,
  onSelect,
}: {
  feed: Feed;
  active?: boolean;
  onSelect: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onSelect}
      className={cn(
        "flex w-full items-baseline gap-1.5 rounded-md px-2 py-1 text-left text-xs transition-colors hover:bg-sidebar-accent/60",
        active ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground/85",
      )}
    >
      <span className="shrink-0 text-sidebar-foreground/45" aria-hidden>
        •
      </span>
      <span className="min-w-0 truncate">{feed.title || feed.url}</span>
      {feed.unread_count ? (
        <span className="ml-auto shrink-0 tabular-nums text-[10px] text-sidebar-foreground/55">{feed.unread_count}</span>
      ) : null}
    </button>
  );
}
