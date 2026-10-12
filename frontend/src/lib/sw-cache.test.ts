import assert from "node:assert/strict";
import test from "node:test";
import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";
import vm from "node:vm";

/**
 * Minimal VM harness for the hand-rolled service worker (public/sw.js).
 *
 * The repo had no sw test before this slice, so this is the minimal harness:
 * load sw.js into a VM with fake `self`/`caches`/`fetch`/`Headers`/`Request`/
 * `Response`/`URL` globals, capture the installed event listeners, and drive
 * fetch events through them. The worker source itself is unmodified — the
 * harness only supplies browser globals it cannot get under node --test.
 */

const SW_SOURCE = readFileSync(
  fileURLToPath(new URL("../../public/sw.js", import.meta.url)),
  "utf8",
);

type FetchListener = (event: {
  request: Request;
  respondWith: (p: Promise<Response>) => void;
  waitUntil?: (p: Promise<unknown>) => void;
}) => void;

type Harness = {
  dispatchFetch: (request: Request) => Promise<Response | null>;
  postMessage: (data: unknown) => void;
  cachePuts: Array<{ url: string; response: Response }>;
  networkMode: { fail: boolean; failFor?: (url: string) => boolean };
};

function loadHarness(): Harness {
  const fetchListeners: FetchListener[] = [];
  const messageListeners: Array<(event: { data: unknown; waitUntil?: (p: Promise<unknown>) => void }) => void> = [];
  const cachePuts: Array<{ url: string; response: Response }> = [];
  const cacheEntries = new Map<string, Response>();
  const networkMode: { fail: boolean; failFor?: (url: string) => boolean } = { fail: false };

  const fakeSelf = {
    location: { origin: "https://tauri.localhost" },
    addEventListener: (type: string, listener: unknown) => {
      if (type === "fetch") fetchListeners.push(listener as FetchListener);
      if (type === "message") messageListeners.push(listener as (e: { data: unknown }) => void);
    },
    skipWaiting: () => {},
    clients: { claim: () => {} },
  };

  const fakeCaches = {
    open: async () => ({
      match: async (request: Request | string) => {
        const key = typeof request === "string" ? request : request.url;
        return cacheEntries.get(key) ?? undefined;
      },
      put: async (request: Request | string, response: Response) => {
        const key = typeof request === "string" ? request : request.url;
        cachePuts.push({ url: key, response });
        cacheEntries.set(key, response);
      },
      add: async () => {},
    }),
    keys: async () => [],
    delete: async () => true,
  };

  // Every successful network response carries an incrementing seq, so a test
  // can prove a served response is the CACHED copy (seq 0) rather than a
  // fresh one (a later seq).
  let networkSeq = 0;

  const fakeFetch = async (input: RequestInfo | URL) => {
    const url = String(input);
    if (networkMode.fail || networkMode.failFor?.(url)) {
      throw new TypeError("Failed to fetch (offline)");
    }
    networkSeq += 1;
    return new Response(JSON.stringify({ seq: networkSeq - 1 }), {
      status: 200,
      headers: { "content-type": "application/json" },
    });
  };

  const sandbox = {
    self: fakeSelf,
    caches: fakeCaches,
    fetch: fakeFetch,
    Request,
    Response,
    Headers,
    URL,
    setTimeout,
    clearTimeout,
    console,
  };

  vm.createContext(sandbox);
  vm.runInContext(SW_SOURCE, sandbox, { filename: "sw.js" });

  return {
    cachePuts,
    networkMode,
    dispatchFetch: async (request: Request) => {
      let captured: Promise<Response> | null = null;
      const event = {
        request,
        respondWith: (p: Promise<Response>) => {
          captured = p;
        },
        waitUntil: () => {},
      };
      for (const listener of fetchListeners) listener(event);
      return captured ? await captured : null;
    },
    postMessage: (data: unknown) => {
      for (const listener of messageListeners) {
        listener({ data, waitUntil: () => {} });
      }
    },
  };
}

const CONVERSATIONS_URL = "https://tauri.localhost/api/v1/chat/conversations";
const CONVERSATION_DETAIL_URL = `${CONVERSATIONS_URL}/bde4cd80-2f69-42b9-a548-74db50522a1f`;
// NOTE: there is NO GET .../messages endpoint — messages are embedded in the
// conversation detail response (POST .../messages only sends). Detail is the
// real read path, so the detail GET is what must be cached.
const CONVERSATIONS_EXPORT_URL = `${CONVERSATIONS_URL}-export`;
const JUNIOR_URL = "https://tauri.localhost/api/v1/junior/documents";
const OTHER_API_URL = "https://tauri.localhost/api/v1/me";

test("a chat conversations GET goes through the stale-while-revalidate path", async () => {
  const harness = loadHarness();
  const response = await harness.dispatchFetch(new Request(CONVERSATIONS_URL));
  assert.ok(response, "the conversations list must be handled by the SW");
  assert.equal(response.status, 200);
  assert.ok(
    harness.cachePuts.some((put) => put.url === CONVERSATIONS_URL),
    "the conversations response must be written to the API cache",
  );
});

test("a conversation detail GET is cached, but a sibling -export route is not", async () => {
  const harness = loadHarness();
  await harness.dispatchFetch(new Request(CONVERSATION_DETAIL_URL));
  await harness.dispatchFetch(new Request(CONVERSATIONS_EXPORT_URL));
  const cached = harness.cachePuts.map((put) => put.url);
  assert.ok(cached.includes(CONVERSATION_DETAIL_URL), "the conversation detail must be cached");
  assert.ok(
    !cached.includes(CONVERSATIONS_EXPORT_URL),
    "the prefix match must not swallow sibling routes like /conversations-export",
  );
});

test("the conversations list is served from cache when the network fails", async () => {
  const harness = loadHarness();
  // Warm the cache online first (seq 0).
  const fresh = await harness.dispatchFetch(new Request(CONVERSATIONS_URL));
  assert.equal(fresh?.status, 200);
  assert.deepEqual(await fresh?.json(), { seq: 0 });
  // Now go offline: the cached copy must still answer, and it must be the
  // ORIGINAL response (seq 0), not a fresh fetch.
  harness.networkMode.fail = true;
  const stale = await harness.dispatchFetch(new Request(CONVERSATIONS_URL));
  assert.ok(stale, "an offline conversations GET must resolve from cache");
  assert.equal(stale.status, 200);
  assert.deepEqual(await stale.json(), { seq: 0 }, "the served body is the cached copy");
});

test("a POST to /api/v1/chat/conversations stays network-only (never cached)", async () => {
  const harness = loadHarness();
  const post = new Request(CONVERSATIONS_URL, { method: "POST" });
  const handled = await harness.dispatchFetch(post);
  assert.equal(handled, null, "the SW must not respondWith() for the mutation");
  assert.equal(
    harness.cachePuts.filter((put) => put.url === CONVERSATIONS_URL).length,
    0,
    "a POST must never be written to the cache",
  );
});

test("the pre-existing /api/v1/junior/ SWR prefix still works", async () => {
  const harness = loadHarness();
  const fresh = await harness.dispatchFetch(new Request(JUNIOR_URL));
  assert.equal(fresh?.status, 200);
  assert.ok(harness.cachePuts.some((put) => put.url === JUNIOR_URL));
  harness.networkMode.fail = true;
  const stale = await harness.dispatchFetch(new Request(JUNIOR_URL));
  assert.ok(stale, "a junior GET must still be served stale offline");
});

test("other API GETs (e.g. /api/v1/me) stay network-only", async () => {
  const harness = loadHarness();
  const handled = await harness.dispatchFetch(new Request(OTHER_API_URL));
  assert.equal(handled, null, "non-junior, non-conversation API GETs are not SW-intercepted");
  assert.equal(
    harness.cachePuts.filter((put) => put.url === OTHER_API_URL).length,
    0,
    "other API responses must never be cached",
  );
});
