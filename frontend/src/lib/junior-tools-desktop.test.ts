import assert from "node:assert/strict";
import test from "node:test";

// A packaged build inlines NEXT_PUBLIC_API_ORIGIN at build time; set it BEFORE
// junior-tools (which statically imports api-base) is loaded, so apiUrl()
// resolves the app-relative tool paths against the API origin — the packaged
// desktop window case this test exists for. With the env unset apiUrl() is a
// dev no-op, which is what junior-tools.test.ts exercises.
//
// This must live in its own file (not appended to junior-tools.test.ts)
// because that file's static `@/lib/junior-tools` import would evaluate
// api-base before any top-level statement here could set the variable.
process.env.NEXT_PUBLIC_API_ORIGIN = "https://storykeep-production.up.railway.app";

const ORIGIN = "https://storykeep-production.up.railway.app";

// Simulate the packaged desktop window: the app origin (tauri.localhost)
// differs from the API origin (Railway), which is what unlocks bearer-token
// storage — the same simulation api-base.test.ts uses.
if (typeof globalThis.window === "undefined") {
  Object.defineProperty(globalThis, "window", {
    value: { location: { origin: "https://tauri.localhost" } },
    configurable: true,
  });
}

type FetchCall = { url: string; headers: Headers; init?: RequestInit };

function stubFetch(): { calls: FetchCall[]; restore: () => void } {
  const calls: FetchCall[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), headers: new Headers(init?.headers), init });
    return {
      ok: true,
      status: 200,
      statusText: "OK",
      json: async () => [],
    } as unknown as Response;
  }) as typeof fetch;
  return { calls, restore: () => { globalThis.fetch = original; } };
}

test("every Junior tool call fetches the apiUrl-resolved absolute URL", async () => {
  const { runJuniorTool } = await import("./junior-tools");
  const stub = stubFetch();
  try {
    // One GET and one POST handler: every tool goes through the same
    // toolFetch, so these two cover the whole surface.
    await runJuniorTool("list_drafts", "{}");
    await runJuniorTool("create_task", '{"kind":"hermes_work","title":"T","instructions":"I"}');
    assert.ok(stub.calls.length >= 2, "both tools must issue a fetch");
    for (const call of stub.calls) {
      assert.ok(
        call.url.startsWith(`${ORIGIN}/api/v1/`),
        `tool fetch must be origin-resolved, got ${call.url}`,
      );
    }
    assert.equal(stub.calls[0]?.url, `${ORIGIN}/api/v1/junior/email/drafts?limit=10`);
    // The POST keeps its own Content-Type (an explicit init header always
    // wins over the derived auth headers).
    assert.equal(stub.calls[1]?.init?.method, "POST");
    assert.equal(stub.calls[1]?.headers.get("Content-Type"), "application/json");
  } finally {
    stub.restore();
  }
});

test("toolFetch attaches the desktop bearer once a token is set", async () => {
  const { runJuniorTool } = await import("./junior-tools");
  const base = await import("./api-base");
  const stub = stubFetch();
  try {
    // No token (web app, or the desktop window before login): cookie only.
    await runJuniorTool("list_feeds", "{}");
    assert.equal(stub.calls[0]?.url, `${ORIGIN}/api/v1/feeds`);
    assert.equal(stub.calls[0]?.headers.get("Authorization"), null);

    // Desktop window with a login token: the SameSite=Lax cookie is not sent
    // cross-site from tauri.localhost, so the bearer is what authenticates.
    base.setAuthToken("desktop-token");
    await runJuniorTool("list_feeds", "{}");
    assert.equal(stub.calls[1]?.url, `${ORIGIN}/api/v1/feeds`);
    assert.equal(stub.calls[1]?.headers.get("Authorization"), "Bearer desktop-token");

    // Logout clears it again — no token may linger in memory.
    base.setAuthToken(null);
    await runJuniorTool("list_feeds", "{}");
    assert.equal(stub.calls[2]?.headers.get("Authorization"), null);
  } finally {
    stub.restore();
  }
});

test("a raw relative path is never fetched (the desktop 404 regression)", async () => {
  const { runJuniorTool } = await import("./junior-tools");
  const stub = stubFetch();
  try {
    await runJuniorTool("get_document", '{"slug":"quantum-intro"}');
    const call = stub.calls[0];
    assert.ok(call, "get_document must fetch");
    assert.ok(!call.url.startsWith("/"), `relative path leaked to fetch: ${call.url}`);
    assert.equal(call.url, `${ORIGIN}/api/v1/junior/documents/quantum-intro`);
  } finally {
    stub.restore();
  }
});
