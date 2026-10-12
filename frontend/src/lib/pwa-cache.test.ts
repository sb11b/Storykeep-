import assert from "node:assert/strict";
import test from "node:test";

/**
 * Regression tests for the frozen "Opening..." button in the packaged Tauri
 * window.
 *
 * On the desktop window (tauri.localhost / WebView2) `navigator.serviceWorker
 * .ready` can stay pending forever. clearPwaApiCaches() used to await it on
 * the login/logout path *before* `router.replace()`, so navigation never
 * happened and the button hung on "Opening...". The fix: the service-worker
 * notification is fire-and-forget and internally timeout-bounded, and the
 * function's returned promise never depends on it.
 */

type PostMessageSpy = (message: unknown) => void;

type Stub = {
  caches: { keys: () => Promise<string[]>; delete: (key: string) => Promise<boolean> };
  deletedKeys: string[];
  posted: unknown[];
};

function installStubs(options: { ready: Promise<unknown> | undefined; cacheKeys?: string[] }): Stub {
  const deletedKeys: string[] = [];
  const posted: unknown[] = [];
  const postMessage: PostMessageSpy = (message) => posted.push(message);

  const cacheKeys = options.cacheKeys ?? ["storykeep-v1-api", "storykeep-static", "next-data"];
  const caches = {
    keys: async () => [...cacheKeys],
    delete: async (key: string) => {
      deletedKeys.push(key);
      return true;
    },
  };

  Object.defineProperty(globalThis, "caches", { value: caches, configurable: true });

  const serviceWorker =
    options.ready === undefined
      ? undefined
      : {
          ready: options.ready,
        };
  Object.defineProperty(globalThis, "navigator", {
    value: serviceWorker === undefined ? {} : { serviceWorker },
    configurable: true,
  });

  return {
    caches,
    deletedKeys,
    posted,
  };
}

function restore() {
  delete (globalThis as { caches?: unknown }).caches;
  // Restore Node's own navigator global for other tests in this process.
  Object.defineProperty(globalThis, "navigator", {
    value: { userAgent: "node", hardwareConcurrency: 1 },
    configurable: true,
  });
}

/** Resolve with "resolved"/"timeout" so a hang is reported, not just slow. */
async function resolveWithin<T>(promise: Promise<T>, ms: number): Promise<"resolved" | "timeout"> {
  let timer: NodeJS.Timeout | undefined;
  try {
    return await Promise.race([
      promise.then(() => "resolved" as const),
      new Promise<"timeout">((resolve) => {
        timer = setTimeout(() => resolve("timeout"), ms);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}

test("clearPwaApiCaches resolves even when serviceWorker.ready never resolves", async () => {
  // The exact Tauri/WebView2 hang: a permanently pending ready promise.
  const never = new Promise<unknown>(() => {});
  const stub = installStubs({ ready: never });
  const { clearPwaApiCaches } = await import("./pwa-cache");
  try {
    const outcome = await resolveWithin(clearPwaApiCaches(), 2000);
    assert.equal(
      outcome,
      "resolved",
      "clearPwaApiCaches must not wait on a never-resolving serviceWorker.ready",
    );
    // The caches still get cleared — only the SW notification is dropped.
    assert.deepEqual(stub.deletedKeys, ["storykeep-v1-api"]);
  } finally {
    restore();
  }
});

test("clearPwaApiCaches does not block the caller for the SW timeout", async () => {
  const never = new Promise<unknown>(() => {});
  installStubs({ ready: never });
  const { clearPwaApiCaches } = await import("./pwa-cache");
  try {
    const started = Date.now();
    await clearPwaApiCaches();
    const elapsed = Date.now() - started;
    assert.ok(
      elapsed < 500,
      `clearPwaApiCaches took ${elapsed}ms; it must resolve as soon as the Cache API deletes finish`,
    );
  } finally {
    restore();
  }
});

test("clearPwaApiCaches still notifies the service worker when ready resolves", async () => {
  const posted: unknown[] = [];
  const ready = Promise.resolve({
    active: { postMessage: (message: unknown) => posted.push(message) },
  });
  const stub = installStubs({ ready });
  const { clearPwaApiCaches } = await import("./pwa-cache");
  try {
    await clearPwaApiCaches();
    // Fire-and-forget: give the background notification a few ticks.
    for (let i = 0; i < 50 && posted.length === 0; i += 1) {
      await new Promise((resolve) => setImmediate(resolve));
    }
    assert.deepEqual(posted, [{ type: "auth-change" }]);
    assert.deepEqual(stub.deletedKeys, ["storykeep-v1-api"]);
  } finally {
    restore();
  }
});

test("clearPwaApiCaches is safe with no service worker and no caches", async () => {
  installStubs({ ready: undefined });
  const { clearPwaApiCaches } = await import("./pwa-cache");
  try {
    assert.equal(await resolveWithin(clearPwaApiCaches(), 2000), "resolved");
  } finally {
    restore();
  }
  delete (globalThis as { caches?: unknown }).caches;
  assert.equal(await resolveWithin(clearPwaApiCaches(), 2000), "resolved");
  restore();
});
