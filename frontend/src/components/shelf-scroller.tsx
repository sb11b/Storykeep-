"use client";

import { forwardRef, useEffect, useImperativeHandle, useRef, type ReactNode } from "react";

export type ShelfScrollerHandle = {
  getScrollTop: () => number;
  scrollTo: (top: number) => void;
  scrollToIndex: (index: number) => void;
};

/** Native overflow list pane. Never wrap this in Base UI ScrollArea. */
export const ShelfScroller = forwardRef<
  ShelfScrollerHandle,
  {
    shelfKey: string;
    listEpoch: number;
    restoreTop: number | null;
    hasMore: boolean;
    loadingMore?: boolean;
    loaded: number;
    total: number;
    onNearEnd: () => void;
    onScrollTop?: (top: number, userInitiated: boolean) => void;
    onListReset?: (payload: { feed: string; offset: number; startIndex: number }) => void;
    children: ReactNode;
  }
>(function ShelfScroller(
  {
    shelfKey,
    listEpoch,
    restoreTop,
    hasMore,
    loadingMore,
    loaded,
    total,
    onNearEnd,
    onScrollTop,
    onListReset,
    children,
  },
  ref,
) {
  const rootRef = useRef<HTMLDivElement>(null);
  const onNearEndRef = useRef(onNearEnd);
  const onListResetRef = useRef(onListReset);
  const hasMoreRef = useRef(hasMore);
  const userScrolledRef = useRef(false);
  const programmaticRef = useRef(false);
  const paginationReadyRef = useRef(false);
  const suppressNearEndRef = useRef(false);

  const resetScroll = (notify = false) => {
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
        programmaticRef.current = false;
        paginationReadyRef.current = true;
        window.setTimeout(() => {
          suppressNearEndRef.current = false;
        }, 120);
        if (notify) {
          onListResetRef.current?.({ feed: shelfKey, offset: 0, startIndex: 0 });
        }
      });
    });
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
      scrollToIndex: (_index: number) => {
        resetScroll(false);
      },
    }),
    [shelfKey],
  );

  useEffect(() => {
    onNearEndRef.current = onNearEnd;
    onListResetRef.current = onListReset;
    hasMoreRef.current = hasMore;
  }, [onNearEnd, onListReset, hasMore]);

  useEffect(() => {
    resetScroll(false);
  }, [shelfKey]);

  useEffect(() => {
    resetScroll(true);
  }, [listEpoch]);

  useEffect(() => {
    if (restoreTop == null) return;
    const root = rootRef.current;
    if (!root) return;
    suppressNearEndRef.current = true;
    programmaticRef.current = true;
    root.scrollTo({ top: Math.max(0, restoreTop) });
    userScrolledRef.current = restoreTop > 0;
    window.requestAnimationFrame(() => {
      programmaticRef.current = false;
      paginationReadyRef.current = true;
      window.setTimeout(() => {
        suppressNearEndRef.current = false;
      }, 120);
    });
  }, [restoreTop]);

  useEffect(() => {
    const root = rootRef.current;
    if (!root) return;
    const onScroll = () => {
      if (!programmaticRef.current) {
        if (root.scrollTop > 0) userScrolledRef.current = true;
        onScrollTop?.(root.scrollTop, userScrolledRef.current);
      }
      if (!paginationReadyRef.current) return;
      if (suppressNearEndRef.current) return;
      if (!hasMoreRef.current) return;
      if (!userScrolledRef.current) return;
      if (root.clientHeight < 48) return;
      if (root.scrollHeight <= root.clientHeight + 24) return;
      if (root.scrollTop + root.clientHeight >= root.scrollHeight - 140) onNearEndRef.current();
    };
    root.addEventListener("scroll", onScroll, { passive: true });
    return () => root.removeEventListener("scroll", onScroll);
  }, [onScrollTop, shelfKey]);

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
});
