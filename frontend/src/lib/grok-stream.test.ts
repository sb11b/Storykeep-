import assert from "node:assert/strict";
import test from "node:test";
import { ApiError } from "@/lib/api";
import {
  GROK_ARTICLE_INCLUDE_HINT_MAX,
  GROK_STREAM_FIRST_BYTE_MS,
  readGrokChatStream,
  shouldIncludeArticle,
  startChatFirstByteWatchdog,
} from "./grok-stream";

function sseResponse(chunks: string[]): Response {
  const encoder = new TextEncoder();
  let index = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index >= chunks.length) {
        controller.close();
        return;
      }
      controller.enqueue(encoder.encode(chunks[index++]));
    },
  });
  return new Response(stream);
}

test("first-byte budget allows heavy attachment turns", () => {
  assert.equal(GROK_STREAM_FIRST_BYTE_MS, 60_000);
});

test("first-byte watchdog becomes xAI silent", async () => {
  const watch = startChatFirstByteWatchdog(undefined, 40);
  await new Promise((resolve) => setTimeout(resolve, 80));
  assert.equal(watch.silent(), true);
  assert.throws(
    () => watch.throwIfSilent(new DOMException("Aborted", "AbortError")),
    (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 504);
      assert.match(error.message, /xAI silent/);
      return true;
    },
  );
  watch.disarm();
});

test("user abort is not xAI silent", () => {
  const user = new AbortController();
  const watch = startChatFirstByteWatchdog(user.signal, 5_000);
  user.abort();
  assert.equal(watch.silent(), false);
  assert.throws(
    () => watch.throwIfSilent(new DOMException("Chat aborted", "AbortError")),
    (error: unknown) => error instanceof DOMException && error.name === "AbortError",
  );
  watch.disarm();
});

test("shouldIncludeArticle still includes huge bodies as a slice", () => {
  const huge = "x".repeat(GROK_ARTICLE_INCLUDE_HINT_MAX + 1);
  assert.deepEqual(shouldIncludeArticle(true, "art-1", huge), {
    include: true,
    skippedHuge: true,
  });
  assert.deepEqual(shouldIncludeArticle(true, "art-1", "hello"), {
    include: true,
    skippedHuge: false,
  });
  assert.deepEqual(shouldIncludeArticle(false, "art-1", huge), {
    include: false,
    skippedHuge: false,
  });
});

test("readGrokChatStream aborts immediately when the caller cancels", async () => {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode('data: {"delta":"Hel"}\n\n'));
    },
  });
  const abort = new AbortController();
  const pending = readGrokChatStream(new Response(stream), { onDelta: () => {} }, abort.signal);
  abort.abort();
  await assert.rejects(pending, (error: unknown) => error instanceof DOMException && error.name === "AbortError");
});

test("readGrokChatStream delivers deltas", async () => {
  const parts: string[] = [];
  await readGrokChatStream(
    sseResponse(['data: {"delta":"Hel"}\n\n', 'data: {"delta":"lo"}\n\n', "data: [DONE]\n\n"]),
    { onDelta: (text) => parts.push(text) },
  );
  assert.deepEqual(parts, ["Hel", "lo"]);
});

test("readGrokChatStream first-byte timeout is xAI silent", async () => {
  const hanging = new ReadableStream<Uint8Array>({
    start() {
      /* never enqueue */
    },
  });
  await assert.rejects(
    () =>
      readGrokChatStream(
        new Response(hanging),
        { onDelta: () => {} },
        undefined,
        { firstByteMs: 80, idleAfterMs: 5000 },
      ),
    (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 504);
      assert.match(error.message, /xAI silent/);
      return true;
    },
  );
});

test("readGrokChatStream idle timeout when stream sends nothing", async () => {
  const hanging = new ReadableStream<Uint8Array>({
    start() {
      /* never enqueue */
    },
  });
  await assert.rejects(
    () =>
      readGrokChatStream(
        new Response(hanging),
        { onDelta: () => {} },
        undefined,
        { idleMs: 80, hardMs: 5000 },
      ),
    (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 504);
      assert.match(error.message, /xAI silent/);
      return true;
    },
  );
});

test("readGrokChatStream does not hard-kill after tokens start", async () => {
  const encoder = new TextEncoder();
  let step = 0;
  const stream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      if (step === 0) {
        controller.enqueue(encoder.encode('data: {"delta":"Hel"}\n\n'));
        step = 1;
        return;
      }
      if (step === 1) {
        await new Promise((resolve) => setTimeout(resolve, 120));
        controller.enqueue(encoder.encode('data: {"delta":"lo"}\n\n data: [DONE]\n\n'));
        step = 2;
        return;
      }
      controller.close();
    },
  });
  const parts: string[] = [];
  await readGrokChatStream(new Response(stream), { onDelta: (text) => parts.push(text) }, undefined, {
    firstByteMs: 50,
    hardMs: 80,
    idleAfterMs: 1000,
  });
  assert.deepEqual(parts, ["Hel", "lo"]);
});

test("readGrokChatStream keeps tokens when a partial 504 arrives", async () => {
  const parts: string[] = [];
  await assert.rejects(
    () =>
      readGrokChatStream(
        sseResponse([
          'data: {"delta":"Partial "}\n\n',
          'data: {"delta":"answer"}\n\n',
          'data: {"error":"Chat failed (HTTP 504): Chat timed out after 45s.","status":504,"partial":true,"message":"Chat timed out after 45s."}\n\n',
        ]),
        { onDelta: (text) => parts.push(text) },
      ),
    (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 504);
      assert.equal(error.partial, true);
      assert.match(error.message, /timed out after 45s/);
      return true;
    },
  );
  assert.deepEqual(parts, ["Partial ", "answer"]);
});

test("readGrokChatStream parses a leftover event without a blank line", async () => {
  const parts: string[] = [];
  await readGrokChatStream(sseResponse(['data: {"delta":"Hi"}']), { onDelta: (text) => parts.push(text) });
  assert.deepEqual(parts, ["Hi"]);
});

test("readGrokChatStream forwards working then writing stream_status", async () => {
  const meta: Array<{ stream_status?: string; reasoning_effort?: string; model?: string }> = [];
  const parts: string[] = [];
  await readGrokChatStream(
    sseResponse([
      'data: {"stream_status":"working","model":"grok-4.6","reasoning_effort":"low"}\n\n',
      'data: {"stream_status":"writing","delta":"Hi"}\n\n',
      "data: [DONE]\n\n",
    ]),
    {
      onDelta: (text) => parts.push(text),
      onMeta: (item) => meta.push(item),
    },
  );
  assert.equal(meta[0]?.stream_status, "working");
  assert.equal(meta[0]?.reasoning_effort, "low");
  assert.equal(meta[1]?.stream_status, "writing");
  assert.deepEqual(parts, ["Hi"]);
});

test("readGrokChatStream forwards searching stream_status and toast", async () => {
  const meta: Array<{ stream_status?: string; toast?: string }> = [];
  const parts: string[] = [];
  await readGrokChatStream(
    sseResponse([
      'data: {"stream_status":"searching","model":"grok-4.6"}\n\n',
      'data: {"toast":"no public hits; answering from training.","toast_kind":"message"}\n\n',
      'data: {"stream_status":"writing","delta":"From training"}\n\n',
      "data: [DONE]\n\n",
    ]),
    {
      onDelta: (text) => parts.push(text),
      onMeta: (item) => meta.push(item),
    },
  );
  assert.equal(meta[0]?.stream_status, "searching");
  assert.equal(meta[1]?.toast, "no public hits; answering from training.");
  assert.deepEqual(parts, ["From training"]);
});

test("readGrokChatStream forwards generating stream_status", async () => {
  const meta: Array<{ stream_status?: string; reasoning_effort?: string }> = [];
  const parts: string[] = [];
  await readGrokChatStream(
    sseResponse([
      'data: {"stream_status":"generating","model":"grok-4.6","reasoning_effort":"low"}\n\n',
      'data: {"delta":"Generating the image…\\n\\n"}\n\n',
      "data: [DONE]\n\n",
    ]),
    {
      onDelta: (text) => parts.push(text),
      onMeta: (item) => meta.push(item),
    },
  );
  assert.equal(meta[0]?.stream_status, "generating");
  assert.equal(meta[0]?.reasoning_effort, "low");
  assert.deepEqual(parts, ["Generating the image…\n\n"]);
});

test("generating status extends idle past the 60s text timeout", async () => {
  const encoder = new TextEncoder();
  let step = 0;
  const stream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      if (step === 0) {
        controller.enqueue(
          encoder.encode(
            'data: {"stream_status":"generating","delta":"Generating the image…\\n\\n"}\n\n',
          ),
        );
        step = 1;
        return;
      }
      if (step === 1) {
        await new Promise((resolve) => setTimeout(resolve, 120));
        controller.enqueue(encoder.encode('data: {"delta":"done"}\n\n data: [DONE]\n\n'));
        step = 2;
        return;
      }
      controller.close();
    },
  });
  const parts: string[] = [];
  await readGrokChatStream(new Response(stream), { onDelta: (text) => parts.push(text) }, undefined, {
    firstByteMs: 50,
    idleAfterMs: 80,
  });
  assert.deepEqual(parts, ["Generating the image…\n\n", "done"]);
});

test("searching alone does not count as the first token", async () => {
  const encoder = new TextEncoder();
  const stream = new ReadableStream<Uint8Array>({
    start(controller) {
      controller.enqueue(encoder.encode('data: {"stream_status":"searching"}\n\n'));
      controller.close();
    },
  });
  await assert.rejects(
    () =>
      readGrokChatStream(new Response(stream), { onDelta: () => {} }, undefined, {
        firstByteMs: 80,
        idleAfterMs: 5000,
      }),
    (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.match(error.message, /xAI silent/);
      return true;
    },
  );
});

test("heartbeat does not count as the first token", async () => {
  const hangingChunks = [
    'data: {"heartbeat":true}\n\n',
  ];
  const encoder = new TextEncoder();
  let index = 0;
  const stream = new ReadableStream<Uint8Array>({
    pull(controller) {
      if (index < hangingChunks.length) {
        controller.enqueue(encoder.encode(hangingChunks[index++]));
        return;
      }
    },
  });
  await assert.rejects(
    () =>
      readGrokChatStream(new Response(stream), { onDelta: () => {} }, undefined, {
        firstByteMs: 80,
        idleAfterMs: 5000,
      }),
    (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.match(error.message, /xAI silent/);
      return true;
    },
  );
});

test("thinking SSE is not a token and keeps the stream open past the first-byte cut", async () => {
  const encoder = new TextEncoder();
  let step = 0;
  const stream = new ReadableStream<Uint8Array>({
    async pull(controller) {
      if (step === 0) {
        controller.enqueue(encoder.encode('data: {"stream_status":"thinking"}\n\n'));
        step = 1;
        return;
      }
      if (step === 1) {
        await new Promise((resolve) => setTimeout(resolve, 120));
        controller.enqueue(encoder.encode('data: {"delta":"hello"}\n\n data: [DONE]\n\n'));
        step = 2;
        return;
      }
      controller.close();
    },
  });
  const parts: string[] = [];
  await readGrokChatStream(new Response(stream), { onDelta: (text) => parts.push(text) }, undefined, {
    firstByteMs: 50,
    idleAfterMs: 5_000,
  });
  assert.deepEqual(parts, ["hello"]);
});

test("DONE with no text is an empty close, not a finished reply", async () => {
  await assert.rejects(
    () =>
      readGrokChatStream(
        sseResponse(['data: {"stream_status":"thinking"}\n\n', "data: [DONE]\n\n"]),
        { onDelta: () => {} },
        undefined,
        { firstByteMs: 5_000, idleAfterMs: 5_000 },
      ),
    (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 504);
      return true;
    },
  );
});
