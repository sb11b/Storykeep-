import assert from "node:assert/strict";
import test from "node:test";
import { ApiError } from "@/lib/api";
import {
  GROK_ARTICLE_INCLUDE_HINT_MAX,
  readGrokChatStream,
  shouldIncludeArticle,
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

test("shouldIncludeArticle skips huge bodies", () => {
  const huge = "x".repeat(GROK_ARTICLE_INCLUDE_HINT_MAX + 1);
  assert.deepEqual(shouldIncludeArticle(true, "art-1", huge), {
    include: false,
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

test("readGrokChatStream delivers deltas", async () => {
  const parts: string[] = [];
  await readGrokChatStream(
    sseResponse(['data: {"delta":"Hel"}\n\n', 'data: {"delta":"lo"}\n\n', "data: [DONE]\n\n"]),
    { onDelta: (text) => parts.push(text) },
  );
  assert.deepEqual(parts, ["Hel", "lo"]);
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
      assert.match(error.message, /No response \(timeout\)/);
      return true;
    },
  );
});

test("readGrokChatStream hard timeout", async () => {
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
        { idleMs: 5000, hardMs: 80 },
      ),
    (error: unknown) => {
      assert.ok(error instanceof ApiError);
      assert.equal(error.status, 504);
      assert.match(error.message, /timed out after 45s/);
      return true;
    },
  );
});
