import assert from "node:assert/strict";
import test from "node:test";

// A packaged build inlines NEXT_PUBLIC_API_ORIGIN at build time; set it before
// api-base loads so these tests exercise the absolute-URL path (an unset env
// makes apiUrl a dev no-op, which the rest of the suite runs under).
process.env.NEXT_PUBLIC_API_ORIGIN = "https://storykeep-production.up.railway.app";

const ORIGIN = "https://storykeep-production.up.railway.app";
const ID = "bde4cd80-2f69-42b9-a548-74db50522a1f";

test("apiUrl resolves relative paths against the configured origin", async () => {
  const { apiUrl } = await import("./api-base");
  assert.equal(apiUrl(`/api/v1/media/${ID}`), `${ORIGIN}/api/v1/media/${ID}`);
  assert.equal(apiUrl("api/v1/media"), `${ORIGIN}/api/v1/media`);
});

test("apiUrl leaves absolute URLs and schemes alone", async () => {
  const { apiUrl } = await import("./api-base");
  assert.equal(apiUrl(`${ORIGIN}/api/v1/media/${ID}`), `${ORIGIN}/api/v1/media/${ID}`);
  assert.equal(apiUrl("blob:https://tauri.localhost/1"), "blob:https://tauri.localhost/1");
  assert.equal(apiUrl("//cdn.example/x.png"), "//cdn.example/x.png");
});

test("setAuthToken stores the login token and clears it on logout", async () => {
  // Read through the namespace object (not a destructured binding) so the
  // mutable AUTH_TOKEN export is observed live under tsx's CJS output.
  const base = await import("./api-base");
  assert.equal(base.AUTH_TOKEN, null);
  base.setAuthToken("  token-123  ");
  assert.equal(base.AUTH_TOKEN, "token-123");
  base.setAuthToken(null);
  assert.equal(base.AUTH_TOKEN, null);
  base.setAuthToken("");
  assert.equal(base.AUTH_TOKEN, null);
});

test("resolveChatImageSrc makes server-emitted relative media srcs absolute", async () => {
  const { resolveChatImageSrc, mediaDownloadUrl } = await import("./chat-media-download");
  const relative = `/api/v1/media/${ID}`;
  assert.equal(resolveChatImageSrc(relative), `${ORIGIN}${relative}`);
  // An already-absolute src (the live img in a browser) is never re-prefixed.
  const absolute = `${ORIGIN}${relative}`;
  assert.equal(resolveChatImageSrc(absolute), absolute);
  // The accidental ".jpg" suffix is still stripped, then resolved.
  assert.equal(resolveChatImageSrc(`${relative}.jpg`), `${ORIGIN}${relative}`);
  // A reconstructed id URL goes through the same origin resolution.
  assert.equal(mediaDownloadUrl(ID), `${ORIGIN}${relative}`);
});

test("request() attaches the bearer token once one is set", async () => {
  const { api } = await import("./api");
  const base = await import("./api-base");
  const calls: Array<{ headers: Headers; url: string }> = [];
  const originalFetch = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ headers: new Headers(init?.headers), url: String(input) });
    return new Response("{}", { status: 200, headers: { "content-type": "application/json" } });
  }) as typeof fetch;
  try {
    // No token yet (web app): no Authorization header, cookie session only.
    await api.me();
    assert.equal(calls[0]?.headers.get("Authorization"), null);

    base.setAuthToken("token-abc");
    await api.me();
    assert.equal(calls[1]?.headers.get("Authorization"), "Bearer token-abc");
    // The path itself is still origin-resolved for the packaged window.
    assert.equal(calls[1]?.url, `${ORIGIN}/api/v1/me`);
    base.setAuthToken(null);
  } finally {
    globalThis.fetch = originalFetch;
  }
});
