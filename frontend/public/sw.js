/* eslint-disable no-restricted-globals */
/**
 * StoryKeep service worker — hand-rolled, dependency-free (no Workbox).
 * Lives in public/ so it is served at the root scope (/sw.js).
 *
 * Caching strategy (library-aware):
 *  - app shell + static assets (_next/static, icons, manifest, fonts):
 *      cache-first, precached on install.
 *  - Junior API GETs (/api/v1/junior/* — jobs, memory, chats, documents) and
 *    chat conversation GETs (/api/v1/chat/conversations — list, detail,
 *    messages): stale-while-revalidate — serve cached instantly, refresh in
 *    background. The conversation prefix is what makes the chat sidebar
 *    recall offline in the desktop app.
 *  - POST / PATCH / PUT / DELETE (and any other mutation):
 *      never cached, network-only. Reads may fail when offline; writes never
 *      silently pretend to succeed.
 *  - navigation requests:
 *      network-first with cached-shell fallback when offline.
 *
 * The same cache is what will make the future Tauri wrapper work offline.
 */

const SW_VERSION = "storykeep-v1";
const SHELL_CACHE = `${SW_VERSION}-shell`;
const API_CACHE = `${SW_VERSION}-api`;

/**
 * App shell precached on install. Static assets under /_next/static cannot be
 * enumerated at install time (hashed filenames), so they are cached lazily on
 * first fetch via the cache-first branch in the fetch handler below.
 */
const SHELL_ASSETS = [
  "/",
  "/offline/",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/icon-maskable-512.png",
  "/apple-touch-icon.png",
  "/manifest.webmanifest",
  "/favicon.ico",
];

/** Junior API GET paths that may be served stale-while-revalidate. */
const STALE_WHILE_REVALIDATE_PREFIXES = ["/api/v1/junior/", "/api/v1/chat/conversations"];

const MUTATION_METHODS = new Set(["POST", "PUT", "PATCH", "DELETE"]);

self.addEventListener("install", (event) => {
  event.waitUntil(
    (async () => {
      const cache = await caches.open(SHELL_CACHE);
      // Individual adds so one 404 (e.g. /offline before it exists) cannot
      // fail the whole install.
      await Promise.all(
        SHELL_ASSETS.map((url) =>
          cache.add(new Request(url, { cache: "reload" })).catch(() => {}),
        ),
      );
      await self.skipWaiting();
    })(),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    (async () => {
      const keys = await caches.keys();
      await Promise.all(
        keys
          .filter((key) => !key.startsWith(SW_VERSION))
          .map((key) => caches.delete(key)),
      );
      await self.clients.claim();
    })(),
  );
});

// Auth-change signal from the client (logout / login success): the API cache
// holds user-scoped responses keyed on URL only, so it must be dropped on
// every auth transition or the next user on a shared device inherits the
// previous user's cached library.
//
// "api-origin": the absolute API origin used by packaged builds (Tauri desktop
// window, static export). There the app is served from its own origin and the
// API lives on another one, so the same-origin guard below would skip every API
// request and the library would never cache for offline. The client posts the
// origin once per load (see pwa-register.tsx); empty = dev, same-origin proxy.
let API_ORIGIN = "";
//
// "auth-token": the bearer token for the packaged desktop window, mirrored
// from setAuthToken() in api-base.ts (null on logout). <img src> loads and
// other subresources to the API origin cannot set an Authorization header
// themselves, and SameSite=Lax cookies are not sent on cross-site subresource
// requests — so the worker injects the header for API-origin fetches below.
// Memory-only: this variable lives in the SW global and dies with the browser
// profile. Never set on the web app (cookie session), so nothing is touched
// there.
let AUTH_TOKEN = null;

self.addEventListener("message", (event) => {
  const data = event.data;
  if (data && data.type === "api-origin" && typeof data.origin === "string") {
    API_ORIGIN = data.origin.replace(/\/+$/, "");
  }
  if (data && data.type === "auth-token") {
    AUTH_TOKEN = typeof data.token === "string" && data.token ? data.token : null;
  }
  if (data && data.type === "auth-change") {
    event.waitUntil(caches.delete(API_CACHE));
  }
});

/**
 * Add the bearer token to a request when it is missing. Only ever called for
 * API-origin requests with a token set (the desktop window); the web app
 * keeps its cookie session untouched.
 */
function withBearer(request, mode) {
  if (!AUTH_TOKEN || !API_ORIGIN) return request;
  if (new URL(request.url).origin !== API_ORIGIN) return request;
  if (request.headers.has("Authorization")) return request;
  const headers = new Headers(request.headers);
  headers.set("Authorization", `Bearer ${AUTH_TOKEN}`);
  // An explicit cors mode is required for no-cors subresource loads
  // (<img>): cloning a no-cors request strips Authorization behind the
  // request-no-cors guard, so the header would silently disappear.
  return new Request(request, mode ? { headers, mode } : { headers });
}

self.addEventListener("fetch", (event) => {
  const { request } = event;
  if (request.method !== "GET") {
    // Mutations: straight to the network, never cached, never faked. Still
    // authenticated — a cross-origin POST from the desktop window needs the
    // bearer header the same way an <img> does.
    if (new URL(request.url).origin === API_ORIGIN && AUTH_TOKEN) {
      const authed = withBearer(request);
      if (authed !== request) {
        event.respondWith(fetch(authed));
        return;
      }
    }
    return;
  }

  const url = new URL(request.url);
  const isAppOrigin = url.origin === self.location.origin;
  const isApiOrigin = Boolean(API_ORIGIN) && url.origin === API_ORIGIN;
  if (!isAppOrigin && !isApiOrigin) return;

  // Subresources (avatars, chat pictures, markdown images) to the API origin
  // cannot carry the header themselves — attach it here. The request is then
  // handed to the same strategy functions below, which use it for both the
  // cache key and the network fetch, so the Junior library keeps its
  // stale-while-revalidate caching (the header is per-request, not cached).
  const authed = isApiOrigin && AUTH_TOKEN ? withBearer(request) : request;

  // 1. Navigation requests: network-first, cached shell when offline.
  if (request.mode === "navigate") {
    event.respondWith(navigationStrategy(authed));
    return;
  }

  // 2. Junior API GETs + chat conversation GETs: stale-while-revalidate
  //    (the "library", now plus offline chat recall).
  if (STALE_WHILE_REVALIDATE_PREFIXES.some((p) => url.pathname.startsWith(p))) {
    event.respondWith(staleWhileRevalidate(authed, API_CACHE));
    return;
  }

  // 3. Everything else same-origin (static assets, manifest, icons):
  //    cache-first, filled lazily on first fetch.
  //    API paths (other than the Junior SWR set above) are deliberately NOT
  //    cached: they are user-scoped responses (credentials: include), the
  //    backend sends no Vary header, and the Cache API keys on URL only —
  //    caching them would serve one user's data to the next on a shared
  //    device. The app itself sends cache: 'no-store' on these calls, so
  //    passing them through to the network uncached is the zero-risk default.
  if (url.pathname.startsWith("/api/")) {
    // Non-Junior API GETs: network-only, never cached. But a cross-origin
    // subresource (avatar <img>, chat picture, markdown image) cannot carry
    // the bearer header itself, so when a token is set, respond with an
    // explicitly cors-mode authenticated fetch — a no-cors clone strips
    // Authorization, and without respondWith the browser re-fetches the
    // original headerless request. Still never cached: no cache.put here.
    if (isApiOrigin && AUTH_TOKEN) {
      const authedApi = withBearer(request, "cors");
      if (authedApi !== request) {
        event.respondWith(fetch(authedApi));
        return;
      }
    }
    return; // network-only, never cached
  }
  event.respondWith(cacheFirst(request, SHELL_CACHE));
});

async function navigationStrategy(request) {
  const cache = await caches.open(SHELL_CACHE);
  try {
    const response = await fetch(request);
    // Refresh the cached shell for this URL so the next offline launch is fresh.
    if (response.ok) cache.put(request, response.clone());
    return response;
  } catch {
    const cached =
      (await cache.match(request)) ||
      (await cache.match("/")) ||
      (await cache.match("/offline/")) ||
      (await cache.match("/offline"));
    if (cached) return cached;
    return new Response("Offline — and no cached shell available yet.", {
      status: 503,
      headers: { "Content-Type": "text/plain" },
    });
  }
}

async function staleWhileRevalidate(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  const network = fetch(request)
    .then((response) => {
      if (response.ok) cache.put(request, response.clone());
      return response;
    })
    .catch(() => null);

  // Serve cached instantly; when nothing is cached yet, wait for the network
  // and surface a real error (never fabricated data) if it fails.
  if (cached) return cached;
  const fresh = await network;
  if (fresh) return fresh;
  throw new TypeError("Failed to fetch (offline, no cached copy)");
}

async function cacheFirst(request, cacheName) {
  const cache = await caches.open(cacheName);
  const cached = await cache.match(request);
  if (cached) {
    // Refresh in background so hashed assets pick up on deploy.
    fetch(request)
      .then((response) => {
        if (response.ok) cache.put(request, response.clone());
      })
      .catch(() => {});
    return cached;
  }
  const response = await fetch(request);
  if (response.ok) cache.put(request, response.clone());
  return response;
}
