/**
 * API origin for packaged (static-export) builds.
 *
 * `next dev` proxies `/api/*` to the backend (see the rewrites in
 * `next.config.ts`), so relative paths are correct there and this module is a
 * no-op. A static export has no proxy: the app is served from its own origin
 * (Railway, or `https://tauri.localhost` in the Tauri desktop window), so every
 * API call must be absolute or it 404s against the app origin.
 *
 * `NEXT_PUBLIC_API_ORIGIN` is inlined at build time. `next.config.ts` defaults
 * it to the Railway deployment for `NEXT_OUTPUT=export` builds (and honours an
 * explicit override); dev builds leave it empty so the proxy stays in charge.
 */
const RAW_ORIGIN = (process.env.NEXT_PUBLIC_API_ORIGIN ?? "").trim();

export const API_ORIGIN = RAW_ORIGIN.replace(/\/+$/, "");

/** True for URLs that already carry their own origin/scheme (leave them alone). */
function isAbsoluteUrl(path: string): boolean {
  return /^[a-z][a-z0-9+.-]*:/i.test(path) || path.startsWith("//");
}

/** Resolve an app-relative API path against the configured origin (no-op in dev). */
export function apiUrl(path: string): string {
  if (!API_ORIGIN || isAbsoluteUrl(path)) return path;
  return `${API_ORIGIN}${path.startsWith("/") ? path : `/${path}`}`;
}

/**
 * WebSocket URL for an app-relative path. The backend is reached over TLS in
 * production, so ws becomes wss there; with no configured origin the caller
 * keeps using `window.location` (dev, proxied).
 */
export function apiWsUrl(path: string): string {
  if (!API_ORIGIN || isAbsoluteUrl(path)) return path;
  const scheme = API_ORIGIN.startsWith("https://") ? "wss://" : "ws://";
  const host = API_ORIGIN.replace(/^https?:\/\//, "");
  return `${scheme}${host}${path.startsWith("/") ? path : `/${path}`}`;
}
