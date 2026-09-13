import assert from "node:assert/strict";
import test from "node:test";
import {
  downloadChatPicture,
  liveChatImageSrc,
  mediaDownloadUrl,
  mediaIdFromUrl,
  resolveChatImageSrc,
  sniffImageContentType,
  storykeepDownloadFilename,
} from "./chat-media-download";

test("download names use storykeep-{id} plus a real extension", () => {
  const id = "7b0b925c-1111-4111-8111-111111111111";
  assert.equal(storykeepDownloadFilename(id, "image/jpeg"), `storykeep-${id}.jpg`);
  assert.equal(storykeepDownloadFilename(id, "image/png"), `storykeep-${id}.png`);
  assert.equal(storykeepDownloadFilename(id, "image/webp"), `storykeep-${id}.webp`);
  assert.notEqual(storykeepDownloadFilename(id, "image/jpeg"), "download");
});

test("media ids come from the stable /media URL", () => {
  const id = "11111111-1111-4111-8111-111111111111";
  assert.equal(mediaIdFromUrl(`/api/v1/media/${id}`), id);
  assert.equal(mediaDownloadUrl(id), `/api/v1/media/${id}`);
  assert.equal(sniffImageContentType(Uint8Array.from([0xff, 0xd8, 0xff, 0xe0])), "image/jpeg");
});

test("download URL matches img src and does not append .jpg to the path", () => {
  const id = "bde4cd80-2f69-42b9-a548-74db50522a1f";
  const src = `/api/v1/media/${id}`;
  const originSrc = `https://storykeep-production.up.railway.app/api/v1/media/${id}`;
  const wrong = "11111111-1111-4111-8111-111111111111";
  assert.equal(resolveChatImageSrc(src, wrong), src);
  assert.equal(resolveChatImageSrc(`${src}.jpg`, id), src);
  assert.equal(resolveChatImageSrc("blob:https://example/1", id), "blob:https://example/1");
  assert.equal(resolveChatImageSrc(originSrc), originSrc);
  assert.equal(mediaDownloadUrl(id).endsWith(".jpg"), false);
  assert.equal(
    liveChatImageSrc({ getAttribute: () => src, currentSrc: originSrc }, `/api/v1/media/${wrong}`),
    originSrc,
  );
});

test("download GET uses the live img URL, not a reconstructed media id", async () => {
  const id = "bde4cd80-2f69-42b9-a548-74db50522a1f";
  const wrong = "11111111-1111-4111-8111-111111111111";
  const imgSrc = `https://storykeep-production.up.railway.app/api/v1/media/${id}`;
  const jpeg = Uint8Array.from([0xff, 0xd8, 0xff, 0xe0, 0, 1, 2, 3]);
  const fetched: { url: string; credentials?: RequestCredentials }[] = [];
  const originalFetch = globalThis.fetch;
  const originalCreate = URL.createObjectURL;
  const originalRevoke = URL.revokeObjectURL;
  const originalDocument = globalThis.document;
  const originalWindow = globalThis.window;
  const link = {
    href: "",
    download: "",
    rel: "",
    click() {},
    setAttribute() {},
    remove() {},
  };
  URL.createObjectURL = () => "blob:storykeep-test";
  URL.revokeObjectURL = () => undefined;
  Object.defineProperty(globalThis, "document", {
    configurable: true,
    value: {
      createElement: () => link,
      body: { appendChild: (node: unknown) => node },
    },
  });
  Object.defineProperty(globalThis, "window", {
    configurable: true,
    value: {
      setTimeout: (fn: () => void) => {
        fn();
        return 0;
      },
    },
  });
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    fetched.push({ url: String(input), credentials: init?.credentials });
    return new Response(jpeg, { status: 200, headers: { "content-type": "image/jpeg" } });
  }) as typeof fetch;
  try {
    await downloadChatPicture({
      img: { getAttribute: () => `/api/v1/media/${id}`, currentSrc: imgSrc },
      mediaId: wrong,
      url: `/api/v1/media/${wrong}`,
    });
    assert.equal(fetched.length, 1);
    assert.equal(fetched[0]?.url, imgSrc);
    assert.equal(fetched[0]?.credentials, "include");
    assert.notEqual(fetched[0]?.url, `/api/v1/media/${wrong}`);
    assert.equal(fetched[0]?.url.endsWith(".jpg"), false);
    assert.equal(link.download, `storykeep-${id}.jpg`);
  } finally {
    globalThis.fetch = originalFetch;
    URL.createObjectURL = originalCreate;
    URL.revokeObjectURL = originalRevoke;
    Object.defineProperty(globalThis, "document", { configurable: true, value: originalDocument });
    Object.defineProperty(globalThis, "window", { configurable: true, value: originalWindow });
  }
});
