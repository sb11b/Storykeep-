"use client";

import { useEffect, useRef, type ReactNode } from "react";

/** Native overflow list pane. Never wrap this in Base UI ScrollArea. */
export function ShelfScroller({
  shelfKey,
  hasMore,
  loadingMore,
  loaded,
  total,
  onNearEnd,
  children,
}: {
  shelfKey: string;
  hasMore: boolean;
  loadingMore?: boolean;
  loaded: number;
  total: number;
  onNearEnd: () => void;
  children: ReactNode;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const onNearEndRef = useRef(onNearEnd);
  const hasMoreRef = useRef(hasMore);
  onNearEndRef.current = onNearEnd;
  hasMoreRef.current = hasMore;

  useEffect(() => {
    rootRef.current?.scrollTo({ top: 0 });
  }, [shelfKey]);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const onScroll = () => {
      if (!hasMoreRef.current) return;
      if (root.clientHeight < 48) return;
      if (root.scrollHeight <= root.clientHeight + 24) return;
      if (root.scrollTop + root.clientHeight >= root.scrollHeight - 140) onNearEndRef.current();
    };
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => root.removeEventListener("scroll", onScroll);
  }, [shelfKey]);

  return (
    <div ref={rootRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
      {children}
      {hasMore ? (
        <button
          type="button"
          className="w-full px-4 py-3 text-left text-xs text-muted-foreground hover:bg-accent/40"
          onClick={() => onNearEnd()}
        >
          {loadingMore ? "Loading more…" : `Load more · ${loaded} of ${total}`}
        </button>
      ) : null}
    </div>
  );
}
