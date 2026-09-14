"use client";

import { useEffect, useRef, useState } from "react";
import { ChevronDown, MoreHorizontal, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";
import type { Category, Feed, RssShelf, Shelf } from "@/lib/types";

export function ShelfSwitcher({
  shelf,
  rssShelves,
  activeRssShelfId,
  groupedFeeds,
  onRssShelfChange,
  onAddRssShelf,
  onShelf,
  onAddCategory,
  onAddFeed,
  onRenameCategory,
  onDeleteCategory,
  onChangeFeedCategory,
}: {
  shelf: Shelf;
  rssShelves: RssShelf[];
  activeRssShelfId: string | null;
  groupedFeeds: { groups: { category: Category; feeds: Feed[] }[] };
  onRssShelfChange: (shelfId: string) => void;
  onAddRssShelf: () => void;
  onShelf: (shelf: Shelf) => void;
  onAddCategory: () => void;
  onAddFeed: () => void;
  onRenameCategory: (category: Category) => void;
  onDeleteCategory: (category: Category) => void;
  onChangeFeedCategory: (feed: Feed) => void;
}) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);
  const activeRssShelf = rssShelves.find((row) => row.id === activeRssShelfId) ?? rssShelves[0];

  useEffect(() => {
    function onDoc(event: MouseEvent) {
      if (!menuRef.current?.contains(event.target as Node)) setMenuOpen(false);
    }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  return (
    <div className="px-2 pt-5">
      <div className="mb-2 flex items-center gap-1">
        <div className="relative min-w-0 flex-1" ref={menuRef}>
          <button
            type="button"
            className="flex w-full items-center gap-1 rounded-md border border-sidebar-border bg-sidebar px-2 py-1.5 text-left text-sm font-medium text-sidebar-foreground hover:bg-sidebar-accent/50"
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="min-w-0 flex-1 truncate">{activeRssShelf?.name ?? "Shelf"}</span>
            <ChevronDown className="size-3.5 shrink-0 opacity-60" />
          </button>
          {menuOpen ? (
            <div className="absolute left-0 right-0 top-full z-50 mt-1 rounded-md border border-sidebar-border bg-popover py-1 shadow-lg">
              {rssShelves.map((row) => (
                <button
                  key={row.id}
                  type="button"
                  className={cn(
                    "flex w-full items-center justify-between px-3 py-1.5 text-left text-sm hover:bg-accent",
                    row.id === activeRssShelfId && "bg-accent/70 font-medium",
                  )}
                  onClick={() => {
                    onRssShelfChange(row.id);
                    setMenuOpen(false);
                  }}
                >
                  <span>{row.name}</span>
                  {row.unread_count ? (
                    <span className="text-xs tabular-nums text-muted-foreground">{row.unread_count}</span>
                  ) : null}
                </button>
              ))}
              <div className="my-1 border-t border-border" />
              <button
                type="button"
                className="flex w-full px-3 py-1.5 text-left text-sm text-muted-foreground hover:bg-accent hover:text-foreground"
                onClick={() => {
                  setMenuOpen(false);
                  onAddRssShelf();
                }}
              >
                + New shelf…
              </button>
            </div>
          ) : null}
        </div>
        <Button
          size="icon-xs"
          variant="outline"
          className="shrink-0 border-sidebar-border bg-sidebar text-sidebar-foreground"
          aria-label="Add shelf"
          onClick={onAddRssShelf}
        >
          <Plus className="size-3.5" />
        </Button>
      </div>

      <div className="space-y-3 pb-2">
        {groupedFeeds.groups.map(({ category, feeds: groupFeeds }) => (
          <div key={category.id}>
            <div className="flex items-center gap-0.5">
              <button
                type="button"
                onClick={() => onShelf({ kind: "category", id: category.id })}
                className={cn(
                  "min-w-0 flex-1 rounded-md px-2 py-1 text-left text-sm font-medium transition-colors hover:bg-sidebar-accent/60",
                  shelf.kind === "category" && shelf.id === category.id
                    ? "bg-sidebar-accent text-sidebar-accent-foreground"
                    : "text-sidebar-foreground",
                )}
              >
                <span className="truncate">{category.name}</span>
                {category.unread_count ? (
                  <span className="ml-1 text-[10px] tabular-nums text-sidebar-foreground/55">{category.unread_count}</span>
                ) : null}
              </button>
              {!category.is_system ? (
                <Button
                  size="icon-xs"
                  variant="ghost"
                  className="shrink-0 text-sidebar-foreground/45 hover:text-sidebar-foreground"
                  aria-label={`Category actions for ${category.name}`}
                  onClick={() => {
                    const action = window.prompt(`Rename or delete "${category.name}"`, category.name);
                    if (!action?.trim()) return;
                    if (action.trim().toLowerCase() === "delete") onDeleteCategory(category);
                    else if (action.trim() !== category.name) onRenameCategory({ ...category, name: action.trim() });
                  }}
                >
                  <MoreHorizontal className="size-3.5" />
                </Button>
              ) : null}
            </div>
            {groupFeeds.length ? (
              <ul className="mt-0.5 space-y-0.5 pl-1">
                {groupFeeds.map((feed) => (
                  <li key={feed.id}>
                    <FeedSwitchRow
                      feed={feed}
                      active={shelf.kind === "feed" && shelf.id === feed.id}
                      onSelect={() => onShelf({ kind: "feed", id: feed.id })}
                      onChangeCategory={() => onChangeFeedCategory(feed)}
                    />
                  </li>
                ))}
              </ul>
            ) : null}
          </div>
        ))}
      </div>

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
  onChangeCategory,
}: {
  feed: Feed;
  active?: boolean;
  onSelect: () => void;
  onChangeCategory: () => void;
}) {
  return (
    <div className="flex items-center gap-0.5">
      <button
        type="button"
        onClick={onSelect}
        className={cn(
          "flex min-w-0 flex-1 items-baseline gap-1.5 rounded-md px-2 py-1 text-left text-xs transition-colors hover:bg-sidebar-accent/60",
          active ? "bg-sidebar-accent text-sidebar-accent-foreground" : "text-sidebar-foreground/85",
        )}
      >
        <span className="shrink-0 text-sidebar-foreground/45" aria-hidden>
          •
        </span>
        <span className="min-w-0 truncate">{feed.title || feed.url}</span>
        {feed.last_error ? (
          <span className="ml-auto min-w-0 max-w-[42%] truncate text-[10px] text-destructive" title={feed.last_error}>
            {feed.last_error}
          </span>
        ) : feed.unread_count ? (
          <span className="ml-auto shrink-0 tabular-nums text-[10px] text-sidebar-foreground/55">{feed.unread_count}</span>
        ) : null}
      </button>
      <Button
        size="icon-xs"
        variant="ghost"
        className="shrink-0 text-sidebar-foreground/45 hover:text-sidebar-foreground"
        aria-label={`Change category for ${feed.title || "feed"}`}
        onClick={onChangeCategory}
      >
        <MoreHorizontal className="size-3" />
      </Button>
    </div>
  );
}
