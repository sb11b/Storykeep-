"use client";

import { useEffect, useRef, type ReactNode } from "react";

/** Native overflow list pane. Never wrap this in Base UI ScrollArea. */
export function ShelfScroller({
  shelfKey,
  hasMore,
  onNearEnd,
  children,
}: {
  shelfKey: string;
  hasMore: boolean;
  onNearEnd: () => void;
  children: ReactNode;
}) {
  const rootRef = useRef<HTMLDivElement>(null);
  const sentinelRef = useRef<HTMLDivElement>(null);
  const onNearEndRef = useRef(onNearEnd);
  onNearEndRef.current = onNearEnd;

  useEffect(() => {
    rootRef.current?.scrollTo({ top: 0 });
  }, [shelfKey]);

  useEffect(() => {
    const root = rootRef.current;
    const sentinel = sentinelRef.current;
    if (!root || !sentinel || !hasMore) return;
    const observer = new IntersectionObserver(
      (entries) => {
        if (entries.some((entry) => entry.isIntersecting)) onNearEndRef.current();
      },
      { root, rootMargin: "240px 0px", threshold: 0 },
    );
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, [hasMore, shelfKey]);

  return (
    <div ref={rootRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain">
      {children}
      {hasMore ? <div ref={sentinelRef} className="h-8 shrink-0" aria-hidden /> : null}
    </div>
  );
}
