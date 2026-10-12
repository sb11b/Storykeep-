/**
 * PWA API-cache invalidation on auth transitions.
 *
 * The service worker caches the Junior library (/api/v1/junior/*) with a
 * stale-while-revalidate strategy for offline use. Those responses are
 * user-scoped, and the Cache API keys on URL only — so without an explicit
 * invalidation on every login/logout, the next user on a shared device would
 * inherit the previous user's cached library (even online: SWR serves the
 * cached copy before awaiting the network).
 *
 * A service worker cannot read the HttpOnly session cookie to key the cache
 * per user, so the client layer is the correct fix point: clear the API
 * caches on every auth change, and also tell the active service worker to do
 * the same as belt-and-braces.
 *
 * CRITICAL: this runs on the login/logout path immediately BEFORE
 * navigation. It must never gate a router.replace — in the packaged Tauri
 * window (WebView2) `navigator.serviceWorker.ready` can stay pending forever,
 * and awaiting it froze the "Opening..." button on the desktop sign-in. The
 * service-worker notification is therefore fire-and-forget and internally
 * bounded by a timeout; callers still `void` it rather than awaiting it.
 */

const API_CACHE_SUFFIX = "-api";

/**
 * Hard cap on how long the service-worker notification may take. A packaged
 * WebView2 window can leave `serviceWorker.ready` pending indefinitely, so
 * the ready wait is raced against this and abandoned on timeout.
 */
const SW_READY_TIMEOUT_MS = 1000;

/**
 * Ask the active service worker to drop its API cache too, covering the case
 * where this tab's caches.delete raced the SW's in-flight writes.
 *
 * Never rejects and never waits longer than SW_READY_TIMEOUT_MS: a
 * never-resolving `serviceWorker.ready` (Tauri/WebView2) must not be able to
 * hold up the caller.
 */
async function notifyActiveServiceWorker(): Promise<void> {
  try {
    const ready = navigator?.serviceWorker?.ready;
    if (!ready) return;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const giveUp = new Promise<void>((resolve) => {
      timer = setTimeout(resolve, SW_READY_TIMEOUT_MS);
    });
    try {
      await Promise.race([
        Promise.resolve(ready)
          .then((registration) => registration?.active?.postMessage({ type: "auth-change" }))
          .catch(() => {
            // registration rejected — nothing to notify.
          }),
        giveUp,
      ]);
    } finally {
      if (timer !== undefined) clearTimeout(timer);
    }
  } catch {
    // No active service worker (or unsupported) — nothing to notify.
  }
}

/**
 * Delete every service-worker cache that holds API responses.
 *
 * Resolves as soon as the (fast) Cache API deletes finish; the service-worker
 * notification is kicked off in the background and cannot delay this promise,
 * so awaiting this can no longer stall a navigation. Callers on the
 * navigation path still use `void clearPwaApiCaches()` as defence in depth.
 */
export async function clearPwaApiCaches(): Promise<void> {
  try {
    if (typeof caches === "undefined") return;
    const keys = await caches.keys();
    await Promise.all(
      keys
        .filter((key) => key.endsWith(API_CACHE_SUFFIX))
        .map((key) => caches.delete(key)),
    );
  } catch {
    // Cache clearing is best-effort; the app works online without it.
  }
  // Belt-and-braces: fire-and-forget, and internally timeout-bounded. Never
  // awaited — a hung serviceWorker.ready must never block the caller (this
  // is what froze the desktop "Opening..." button).
  void notifyActiveServiceWorker().catch(() => {
    // notifyActiveServiceWorker already swallows errors; belt-and-braces.
  });
}
