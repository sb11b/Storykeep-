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
 */

const API_CACHE_SUFFIX = "-api";

/** Delete every service-worker cache that holds API responses. */
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
  // Belt-and-braces: ask the active SW to drop its API cache too, covering
  // the case where this tab's caches.delete raced the SW's in-flight writes.
  try {
    const registration = await navigator.serviceWorker?.ready;
    registration?.active?.postMessage({ type: "auth-change" });
  } catch {
    // No active service worker (or unsupported) — nothing to notify.
  }
}
