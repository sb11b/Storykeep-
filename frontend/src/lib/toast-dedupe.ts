/**
 * Toast dedupe.
 *
 * Talk mode auto-submits every committed transcript as a chat message, and the
 * stream-error / stop-generation paths each fire their own toast. When those
 * turns fail back-to-back (or a stale reconnect loop keeps failing), sonner
 * stacks identical toasts and the user sees a rapid-fire popup storm in the
 * bottom-left corner.
 *
 * dedupeToast() remembers the last time each message was shown and suppresses
 * an identical message inside a short window. Different messages always show.
 * State is module-level and never cleared: it only ever suppresses, it can
 * never lose a toast — after the window the same message shows again.
 */

/** Identical toasts closer together than this are collapsed into one. */
export const TOAST_DEDUPE_WINDOW_MS = 2000;

const lastShownAt = new Map<string, number>();

/** Current time — overridable seam for tests. */
function now(): number {
  return Date.now();
}

/**
 * True when `message` has NOT been shown within the window; false when it is a
 * duplicate that should be suppressed. Calling this records the show, so each
 * call is one "attempt".
 */
export function shouldShowToast(
  message: string,
  windowMs: number = TOAST_DEDUPE_WINDOW_MS,
  nowMs: number = now(),
): boolean {
  const previous = lastShownAt.get(message);
  if (previous !== undefined && nowMs - previous < windowMs) return false;
  lastShownAt.set(message, nowMs);
  return true;
}

/** Reset dedupe memory — tests only. */
export function resetToastDedupe(): void {
  lastShownAt.clear();
}

export interface DedupedToast {
  error(message: string): void;
  message(message: string): void;
}

/**
 * Wrap a sonner-style toast object so repeated identical messages collapse
 * within the window. Distinct messages pass through untouched.
 */
export function dedupeToast(toast: DedupedToast, message: string, kind: "error" | "message" = "error"): void {
  if (!shouldShowToast(message)) return;
  if (kind === "error") toast.error(message);
  else toast.message(message);
}
