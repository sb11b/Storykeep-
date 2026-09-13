import assert from "node:assert/strict";
import test from "node:test";
import { ApiError } from "@/lib/api";
import { fetchSpeechChunk } from "@/lib/tts-speech-client";

type FetchStub = typeof globalThis.fetch;

function jsonResponse(status: number, body: unknown) {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => body,
    text: async () => JSON.stringify(body),
  } as unknown as Response;
}

async function withFetch<T>(stub: FetchStub, run: () => Promise<T>): Promise<T> {
  const previous = globalThis.fetch;
  globalThis.fetch = stub;
  try {
    return await run();
  } finally {
    globalThis.fetch = previous;
  }
}

/** Never settles on its own, so only the timeout or a caller abort ends it. */
const hangingFetch = ((_url: string, init?: RequestInit) =>
  new Promise<Response>((_resolve, reject) => {
    init?.signal?.addEventListener("abort", () => reject(new Error("aborted")));
  })) as unknown as FetchStub;

test("fetchSpeechChunk returns audio on success", async () => {
  const payload = await withFetch(
    (async () => jsonResponse(200, { audio: "AAAA", chunks: 1 })) as FetchStub,
    () => fetchSpeechChunk("/tts", { method: "POST" }, "chat", { chars: 12 }),
  );
  assert.equal(payload.chunks, 1);
  assert.ok(payload.blob.size > 0);
});

test("fetchSpeechChunk surfaces the HTTP code for a server failure", async () => {
  await withFetch(
    (async () => jsonResponse(504, { detail: "upstream timeout" })) as FetchStub,
    async () => {
      const error = await fetchSpeechChunk("/tts", { method: "POST" }, "chat").catch((err) => err);
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 504);
      assert.match(error.message, /upstream timeout/);
    },
  );
});

test("fetchSpeechChunk says so when a 200 carries no audio", async () => {
  await withFetch(
    (async () => jsonResponse(200, { audio: "", chunks: 1 })) as FetchStub,
    async () => {
      const error = await fetchSpeechChunk("/tts", { method: "POST" }, "chat").catch((err) => err);
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 200);
      assert.match(error.message, /no audio \(HTTP 200 with an empty body\)/);
    },
  );
});

test("fetchSpeechChunk gives up once the timeout passes", async () => {
  await withFetch(hangingFetch, async () => {
    const error = await fetchSpeechChunk("/tts", { method: "POST" }, "chat", {
      timeoutMs: 20,
    }).catch((err) => err);
    assert.ok(error instanceof ApiError);
    assert.equal(error.status, 408);
    assert.match(error.message, /TTS timed out after 0s \(HTTP … or no body\)/);
  });
});

test("fetchSpeechChunk stops when the caller aborts, without a timeout message", async () => {
  await withFetch(hangingFetch, async () => {
    const controller = new AbortController();
    const pending = fetchSpeechChunk("/tts", { method: "POST" }, "chat", {
      signal: controller.signal,
      timeoutMs: 5_000,
    }).catch((err) => err);
    controller.abort();
    const error = await pending;
    assert.ok(error instanceof Error);
    assert.doesNotMatch(error.message, /timed out/);
  });
});
