"use client";

import { forwardRef, useEffect, useImperativeHandle, useLayoutEffect, useRef, type ReactNode } from "react";

export type ShelfScrollerHandle = {
  getScrollTop: () => number;
  scrollTo: (top: number) => void;
  scrollToIndex: (index: number) => void;
};

function visibleStartIndex(root: HTMLDivElement): number {
  const rows = root.querySelectorAll<HTMLElement>("[data-list-index]");
  if (!rows.length) return 0;
  const rootTop = root.getBoundingClientRect().top;
  for (const row of rows) {
    const rect = row.getBoundingClientRect();
    if (rect.bottom > rootTop + 4) {
      const index = Number(row.dataset.listIndex);
      return Number.isFinite(index) ? index : 0;
    }
  }
  return 0;
}

/** Native overflow list pane. Never wrap this in Base UI ScrollArea. */
export const ShelfScroller = forwardRef<
  ShelfScrollerHandle,
  {
    shelfKey: string;
    listEpoch: number;
    itemCount: number;
    hasMore: boolean;
    loadingMore?: boolean;
    loaded: number;
    total: number;
    onNearEnd: () => void;
    onListPaint?: (payload: { feed: string; offset: number; startIndex: number; count: number }) => void;
    children: ReactNode;
  }
>(function ShelfScroller(
  {
    shelfKey,
    listEpoch,
    itemCount,
    hasMore,
    loadingMore,
    loaded,
    total,
    onNearEnd,
    onListPaint,
    children,
  },
  ref,
) {
  const rootRef = useRef<HTMLDivElement>(null);
  const onNearEndRef = useRef(onNearEnd);
  const onListPaintRef = useRef(onListPaint);
  const hasMoreRef = useRef(hasMore);
  const userScrolledRef = useRef(false);
  const programmaticRef = useRef(false);
  const paginationReadyRef = useRef(false);
  const suppressNearEndRef = useRef(true);
  const lastResetEpochRef = useRef(-1);

  const pinTop = (notify: boolean) => {
    const root = rootRef.current;
    if (!root) return;
    userScrolledRef.current = false;
    paginationReadyRef.current = false;
    suppressNearEndRef.current = true;
    programmaticRef.current = true;
    root.scrollTop = 0;
    window.requestAnimationFrame(() => {
      root.scrollTop = 0;
      window.requestAnimationFrame(() => {
        root.scrollTop = 0;
        scrollToIndex(root, 0);
        programmaticRef.current = false;
        paginationReadyRef.current = true;
        window.setTimeout(() => {
          suppressNearEndRef.current = false;
        }, 600);
        if (notify) {
          onListPaintRef.current?.({
            feed: shelfKey,
            offset: 0,
            startIndex: visibleStartIndex(root),
            count: root.querySelectorAll("[data-list-index]").length,
          });
        }
      });
    });
  };

  const scrollToIndex = (root: HTMLDivElement, index: number) => {
    if (index <= 0) {
      root.scrollTop = 0;
      return;
    }
    const row = root.querySelector<HTMLElement>(`[data-list-index="${index}"]`);
    if (row) row.scrollIntoView({ block: "start" });
    else root.scrollTop = 0;
  };

  useImperativeHandle(
    ref,
    () => ({
      getScrollTop: () => rootRef.current?.scrollTop ?? 0,
      scrollTo: (top: number) => {
        const root = rootRef.current;
        if (!root) return;
        programmaticRef.current = true;
        root.scrollTop = top;
        window.requestAnimationFrame(() => {
          programmaticRef.current = false;
        });
      },
      scrollToIndex: (index: number) => {
        const root = rootRef.current;
        if (!root) return;
        programmaticRef.current = true;
        scrollToIndex(root, index);
        window.requestAnimationFrame(() => {
          programmaticRef.current = false;
        });
      },
    }),
    [],
  );

  useEffect(() => {
    onNearEndRef.current = onNearEnd;
    onListPaintRef.current = onListPaint;
    hasMoreRef.current = hasMore;
  }, [onNearEnd, onListPaint, hasMore]);

  useLayoutEffect(() => {
    userScrolledRef.current = false;
    suppressNearEndRef.current = true;
    const root = rootRef.current;
    if (root) root.scrollTop = 0;
  }, [shelfKey]);

  useLayoutEffect(() => {
    if (listEpoch === lastResetEpochRef.current) return;
    lastResetEpochRef.current = listEpoch;
    pinTop(true);
  }, [listEpoch, shelfKey]);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const unlock = () => {
      if (!programmaticRef.current) userScrolledRef.current = true;
    };
    const onScroll = () => {
      if (!programmaticRef.current && root.scrollTop > 8) {
        userScrolledRef.current = true;
      }
      if (!paginationReadyRef.current) return;
      if (suppressNearEndRef.current) return;
      if (!hasMoreRef.current) return;
      if (!userScrolledRef.current) return;
      if (root.clientHeight < 48) return;
      if (root.scrollHeight <= root.clientHeight + 24) return;
      if (root.scrollTop + root.clientHeight >= root.scrollHeight - 140) onNearEndRef.current();
    };
    root.addEventListener("wheel", unlock, { passive: true });
    root.addEventListener("touchmove", unlock, { passive: true });
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      root.removeEventListener("wheel", unlock);
      root.removeEventListener("touchmove", unlock);
      root.removeEventListener("scroll", onScroll);
    };
  }, [shelfKey]);

  return (
    <div
      ref={rootRef}
      className="min-h-0 flex-1 overflow-y-auto overscroll-contain [overflow-anchor:none]"
      style={{ overflowAnchor: "none" }}
    >
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
});
