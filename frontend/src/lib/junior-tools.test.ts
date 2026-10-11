import assert from "node:assert/strict";
import test from "node:test";
import {
  buildFunctionCallOutput,
  buildResponseCreate,
  DOC_READ_CHARS,
  excerptMarker,
  extractFunctionCall,
  formatDocumentMatches,
  formatDocumentRead,
  formatDraftSaved,
  formatEmailBody,
  formatEmailList,
  formatFileText,
  formatPendingTasks,
  JUNIOR_TOOLS,
  JUNIOR_TOOL_NAMES,
  optionalIntArg,
  parseToolArguments,
  queryTokens,
  documentMatchesQuery,
  requiredStringArg,
  runJuniorTool,
  sliceReadChunk,
} from "@/lib/junior-tools";
import { JUNIOR_TALK_INSTRUCTIONS } from "@/lib/conversation-voice";

/* ── Tool definitions ── */

test("every tool definition is well-formed with unique names", () => {
  assert.ok(JUNIOR_TOOLS.length >= 10);
  const names = JUNIOR_TOOLS.map((tool) => tool.name);
  assert.equal(new Set(names).size, names.length, "tool names must be unique");
  for (const tool of JUNIOR_TOOLS) {
    assert.equal(tool.type, "function");
    assert.ok(tool.name.length > 0);
    assert.ok(tool.description.length > 20, `${tool.name} needs a real description`);
    assert.equal(tool.parameters.type, "object");
    assert.ok(Array.isArray(tool.parameters.required));
    for (const required of tool.parameters.required) {
      assert.ok(
        tool.parameters.properties[required],
        `${tool.name} requires '${required}' but it is not in properties`,
      );
    }
  }
  assert.deepEqual([...names].sort(), [...JUNIOR_TOOL_NAMES].sort(), "handlers cover every tool");
});

test("required parameters are declared for the tools that need them", () => {
  const required = Object.fromEntries(JUNIOR_TOOLS.map((tool) => [tool.name, tool.parameters.required]));
  assert.deepEqual(required.search_library, ["query"]);
  assert.deepEqual(required.get_document, ["slug"]);
  assert.deepEqual(required.read_document_file, ["slug", "file_id"]);
  assert.deepEqual(required.list_feeds, []);
  assert.deepEqual(required.search_articles, []);
  assert.deepEqual(required.read_article, ["id"]);
  assert.deepEqual(required.list_pending_work, []);
  assert.deepEqual(required.create_task, ["kind", "title", "instructions"]);
  assert.deepEqual(required.read_email, []);
  assert.deepEqual(required.search_email, ["query"]);
  assert.deepEqual(required.read_email_message, ["message_id"]);
  assert.deepEqual(required.draft_email, ["to", "subject", "body"]);
  assert.deepEqual(required.list_drafts, []);
});

test("the never-send invariant is baked into the draft tool description", () => {
  const draft = JUNIOR_TOOLS.find((tool) => tool.name === "draft_email");
  assert.ok(draft);
  assert.match(draft!.description, /NEVER claims or implies the email was sent/);
  assert.match(draft!.description, /saved as a draft for him to review and send/);
});

test("get_document's description explains full reads and offset continuation", () => {
  const getDoc = JUNIOR_TOOLS.find((tool) => tool.name === "get_document");
  assert.ok(getDoc);
  assert.match(getDoc!.description, /FULL text/);
  assert.match(getDoc!.description, /READ IT ALOUD/);
  assert.match(getDoc!.description, /increased offset to continue reading/);
  assert.ok(getDoc!.parameters.properties.offset, "get_document exposes an offset parameter");
});

test("read_email_message's description promises the full body for reading aloud", () => {
  const read = JUNIOR_TOOLS.find((tool) => tool.name === "read_email_message");
  assert.ok(read);
  assert.match(read!.description, /FULL body/);
  assert.match(read!.description, /READ IT ALOUD/);
});

/* ── Argument parsing ── */

test("parseToolArguments accepts JSON strings and objects, tolerates garbage", () => {
  assert.deepEqual(parseToolArguments('{"query":"x"}'), { query: "x" });
  assert.deepEqual(parseToolArguments({ query: "x" }), { query: "x" });
  assert.deepEqual(parseToolArguments("not json"), {});
  assert.deepEqual(parseToolArguments(""), {});
  assert.deepEqual(parseToolArguments(undefined), {});
  assert.deepEqual(parseToolArguments("[1,2]"), {});
  assert.deepEqual(parseToolArguments("null"), {});
});

test("requiredStringArg returns null for missing, blank, and non-string values", () => {
  assert.equal(requiredStringArg({ query: "  hello  " }, "query"), "hello");
  assert.equal(requiredStringArg({ query: "   " }, "query"), null);
  assert.equal(requiredStringArg({}, "query"), null);
  assert.equal(requiredStringArg({ query: 42 }, "query"), null);
});

test("optionalIntArg floors and rejects junk", () => {
  assert.equal(optionalIntArg({ offset: 120 }, "offset"), 120);
  assert.equal(optionalIntArg({ offset: 119.9 }, "offset"), 119);
  assert.equal(optionalIntArg({ offset: -5 }, "offset"), 0);
  assert.equal(optionalIntArg({}, "offset"), null);
  assert.equal(optionalIntArg({ offset: "x" }, "offset"), null);
});

/* ── Chunked reads (school texts are long reads) ── */

test("sliceReadChunk slices exactly text[offset:offset+cap]", () => {
  const text = "abcdefghij";
  assert.equal(sliceReadChunk(text, 0, 4), "abcd");
  assert.equal(sliceReadChunk(text, 4, 4), "efgh");
  assert.equal(sliceReadChunk(text, 8, 4), "ij");
  assert.equal(sliceReadChunk(text, 100, 4), "");
  assert.equal(sliceReadChunk("", 0, 4), "");
});

test("chunk round-trip: sequential slices reconstruct the original exactly", () => {
  // A long school-text-sized body, chunked at the document read cap.
  const text = "x".repeat(DOC_READ_CHARS * 2 + 7);
  let offset = 0;
  let rebuilt = "";
  while (offset < text.length) {
    const chunk = sliceReadChunk(text, offset, DOC_READ_CHARS);
    assert.ok(chunk.length > 0);
    rebuilt += chunk;
    offset += chunk.length;
  }
  assert.equal(rebuilt, text, "concatenated chunks must reconstruct the original with no gaps");
});

test("a document read passes full-length text through (no old 2k truncation)", () => {
  const text = "word ".repeat(10_000); // 50k chars — a long article
  const result = formatDocumentRead({ slug: "long-read", title: "Long Read", text });
  assert.equal(result.length > 49_000, true, "a 50k document must be returned essentially in full");
  assert.ok(!result.includes("[excerpt"));
});

test("a document longer than the cap is marked with a speakable excerpt marker", () => {
  const text = "y".repeat(DOC_READ_CHARS + 500);
  const result = formatDocumentRead({ slug: "chapter", title: "Chapter One", text });
  assert.ok(result.includes("[excerpt"));
  assert.ok(result.includes(DOC_READ_CHARS.toLocaleString("en-US")));
});

test("get_document-style offset continues exactly where the previous chunk ended", () => {
  const text = "z".repeat(DOC_READ_CHARS + 100);
  const first = formatDocumentRead({ slug: "s", title: "T", text }, 0);
  const second = formatDocumentRead({ slug: "s", title: "T", text }, DOC_READ_CHARS);
  // The first read holds exactly the first DOC_READ_CHARS characters of text
  // (followed by the speakable continuation marker).
  const firstText = first
    .slice(first.indexOf("Text: ") + "Text: ".length)
    .replace(/ \[excerpt[^\]]*\]$/, "");
  assert.equal(firstText.length, DOC_READ_CHARS, "the first chunk is exactly the read cap");
  assert.equal(firstText, text.slice(0, DOC_READ_CHARS), "the first chunk starts at offset 0");
  assert.ok(first.includes("[excerpt"), "the first chunk announces the continuation");
  // The continuation chunk holds exactly the tail — no dropped or duplicated
  // characters, and it is complete so it needs no continuation marker.
  const secondText = second.slice(second.indexOf("Text: ") + "Text: ".length);
  assert.equal(secondText, text.slice(DOC_READ_CHARS));
  assert.ok(!second.includes("[excerpt"), "the final chunk is complete");
});

test("excerptMarker is speakable and states both numbers", () => {
  const marker = excerptMarker(120_000, 240_000);
  assert.match(marker, /first 120,000 of 240,000 characters/);
  assert.match(marker, /continue/);
});

/* ── Result mapping ── */

test("formatDocumentMatches lists titles, slugs, and summaries", () => {
  const result = formatDocumentMatches([
    { title: "Quantum Intro", slug: "quantum-intro", summary: "A short intro." },
  ]);
  assert.match(result, /"Quantum Intro" \(slug: quantum-intro\)/);
  assert.match(result, /A short intro\./);
});

test("queryTokens and documentMatchesQuery filter documents by title/summary", () => {
  assert.deepEqual(queryTokens("Quantum Physics 101"), ["quantum", "physics", "101"]);
  const doc = { title: "Introduction to Quantum Physics", summary: "superposition" };
  assert.equal(documentMatchesQuery(doc, queryTokens("quantum")), true);
  assert.equal(documentMatchesQuery(doc, queryTokens("medieval")), false);
  assert.equal(documentMatchesQuery(doc, []), true);
});

test("formatPendingTasks summarizes kind, title, status, and approval doc slugs", () => {
  const result = formatPendingTasks([
    { kind: "approval", title: "Review the brief", status: "open", payload: { doc_slug: "meridian-brief" } },
    { kind: "hermes_work", title: "Draft Q3 summary", status: "claimed" },
  ]);
  assert.match(result, /2 things waiting/);
  assert.match(result, /approval — "Review the brief" \(document: meridian-brief\) \[open\]/);
  assert.match(result, /hermes_work — "Draft Q3 summary" \[claimed\]/);
  assert.equal(formatPendingTasks([]), "Nothing is pending — your queue is clear.");
});

test("formatEmailList and formatEmailBody are voice-friendly", () => {
  const list = formatEmailList([
    { from_address: "Jennifer <j@x.com>", subject: "Lunch", unread: true, preview: "Thursday?" },
  ]);
  assert.match(list, /unread, from Jennifer <j@x.com> — "Lunch": Thursday\?/);
  assert.equal(formatEmailList([]), "No email found.");

  const body = formatEmailBody({ from_address: "j@x.com", subject: "Hi", body: "See you Thursday.", excerpt: false });
  assert.match(body, /From j@x.com, "Hi"/);
  assert.match(body, /Body: See you Thursday\./);
  assert.ok(!body.includes("[excerpt"));
  const excerpted = formatEmailBody({ from_address: "j@x.com", subject: "Hi", body: "x".repeat(8_001), excerpt: true });
  assert.ok(excerpted.includes("[excerpt"));
});

test("formatDraftSaved always says the draft is NOT sent", () => {
  const result = formatDraftSaved({ to: "j@x.com", subject: "Re: Lunch" });
  assert.match(result, /Draft saved in Fastmail/);
  assert.match(result, /NOT sent/);
  assert.match(result, /review and send it yourself/);
});

test("formatFileText returns full extracted text and marks excerpts", () => {
  const full = formatFileText({ filename: "chapter.docx", text: "Chapter one body." });
  assert.match(full, /File "chapter.docx"/);
  assert.match(full, /Text: Chapter one body\./);
  assert.ok(!full.includes("[excerpt"));
  const excerpted = formatFileText({ filename: "chapter.docx", text: "q".repeat(30_001), excerpt: true });
  assert.ok(excerpted.includes("[excerpt"));
});

/* ── Event helpers for the function-call loop ── */

test("extractFunctionCall reads the live arguments.done shape", () => {
  const call = extractFunctionCall({
    type: "response.function_call_arguments.done",
    call_id: "call-abc",
    name: "search_library",
    arguments: '{"query":"quantum"}',
  });
  assert.deepEqual(call, { call_id: "call-abc", name: "search_library", arguments: '{"query":"quantum"}' });
});

test("extractFunctionCall reads the item-embedded shape from output_item.done", () => {
  const call = extractFunctionCall({
    type: "response.output_item.done",
    item: {
      type: "function_call",
      call_id: "call-xyz",
      name: "get_document",
      arguments: '{"slug":"quantum-intro"}',
    },
  });
  assert.deepEqual(call, { call_id: "call-xyz", name: "get_document", arguments: '{"slug":"quantum-intro"}' });
});

test("extractFunctionCall ignores deltas, in-progress items, and plain messages", () => {
  // The partial delta event carries `delta`, never the full `arguments`.
  assert.equal(
    extractFunctionCall({
      type: "response.function_call_arguments.delta",
      call_id: "call-1",
      name: "search_library",
      delta: '{"query":',
    }),
    null,
  );
  // The in-progress item carries empty arguments.
  assert.equal(
    extractFunctionCall({
      type: "conversation.item.added",
      item: { type: "function_call", call_id: "call-1", name: "search_library", arguments: "" },
    }),
    null,
  );
  // A completed assistant message item is not a call.
  assert.equal(
    extractFunctionCall({
      type: "response.output_item.done",
      item: { type: "message", role: "assistant" },
    }),
    null,
  );
  assert.equal(extractFunctionCall(null), null);
  assert.equal(extractFunctionCall("nope"), null);
});

test("buildFunctionCallOutput and buildResponseCreate match the live-verified wire shapes", () => {
  assert.deepEqual(buildFunctionCallOutput("call-1", "Found 1 document."), {
    type: "conversation.item.create",
    item: { type: "function_call_output", call_id: "call-1", output: "Found 1 document." },
  });
  assert.deepEqual(buildResponseCreate(), { type: "response.create" });
});

/* ── Handlers (fetch stubbed — no network) ── */

type FetchStub = { calls: Array<{ url: string; init?: RequestInit }>; restore: () => void };

function stubFetch(handler: (url: string) => { ok: boolean; payload: unknown }): FetchStub {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    calls.push({ url, init });
    const { ok, payload } = handler(url);
    return {
      ok,
      status: ok ? 200 : 500,
      statusText: ok ? "OK" : "Error",
      json: async () => payload,
    };
  }) as unknown as typeof fetch;
  return {
    calls,
    restore: () => {
      globalThis.fetch = original;
    },
  };
}

test("runJuniorTool dispatches search_library and merges documents with conversation hits", async () => {
  const stub = stubFetch((url) => {
    if (url.includes("/junior/search")) {
      return {
        ok: true,
        payload: [{ thread_title: "Physics notes", snippet: "We talked about superposition." }],
      };
    }
    return {
      ok: true,
      payload: [
        { slug: "quantum-intro", title: "Introduction to Quantum Physics", summary: "superposition", text: "..." },
        { slug: "meridian-brief", title: "Meridian launch brief", summary: "launch plan" },
      ],
    };
  });
  try {
    const result = await runJuniorTool("search_library", '{"query":"quantum"}');
    assert.match(result, /"Introduction to Quantum Physics" \(slug: quantum-intro\)/);
    assert.match(result, /In "Physics notes": We talked about superposition/);
    assert.ok(!result.includes("meridian-brief"), "non-matching documents are filtered out");
  } finally {
    stub.restore();
  }
});

test("runJuniorTool returns a speakable error for an unknown tool, never throws", async () => {
  const result = await runJuniorTool("delete_everything", "{}");
  assert.match(result, /I don't have a tool called delete_everything/);
});

test("runJuniorTool maps a missing required argument to a speakable prompt", async () => {
  assert.match(await runJuniorTool("get_document", "{}"), /Which document should I pull up/);
  assert.match(await runJuniorTool("search_email", "{}"), /What should I search your email for/);
});

test("runJuniorTool maps endpoint failures to speakable errors", async () => {
  const stub = stubFetch(() => ({ ok: false, payload: null }));
  try {
    assert.match(await runJuniorTool("search_library", '{"query":"x"}'), /couldn't reach your library/);
    assert.match(await runJuniorTool("read_email", "{}"), /can't reach your email/);
    assert.match(await runJuniorTool("list_pending_work", "{}"), /couldn't check the work queue/);
  } finally {
    stub.restore();
  }
});

test("runJuniorTool get_document sends the slug and returns the full read", async () => {
  const stub = stubFetch(() => ({
    ok: true,
    payload: { slug: "quantum-intro", title: "Quantum Intro", summary: "A short intro.", text: "Superposition is real." },
  }));
  try {
    const result = await runJuniorTool("get_document", '{"slug":"quantum-intro"}');
    assert.ok(stub.calls.some((call) => call.url.includes("/junior/documents/quantum-intro")));
    assert.match(result, /"Quantum Intro" \(slug: quantum-intro\)/);
    assert.match(result, /Summary: A short intro\./);
    assert.match(result, /Text: Superposition is real\./);
  } finally {
    stub.restore();
  }
});

test("runJuniorTool get_document passes the offset for continued reads", async () => {
  const stub = stubFetch(() => ({
    ok: true,
    payload: { slug: "chapter", title: "Chapter", text: "z".repeat(DOC_READ_CHARS + 100) },
  }));
  try {
    const result = await runJuniorTool("get_document", `{"slug":"chapter","offset":${DOC_READ_CHARS}}`);
    // The continuation chunk holds exactly the tail.
    assert.match(result, /z{100}/);
    assert.ok(!result.includes("[excerpt"), "the final chunk needs no continuation marker");
  } finally {
    stub.restore();
  }
});

test("runJuniorTool list_pending_work dedupes open and claimed tasks", async () => {
  const stub = stubFetch((url) => {
    if (url.includes("status=claimed")) {
      return { ok: true, payload: [{ id: "t1", kind: "hermes_work", title: "Draft Q3", status: "claimed" }] };
    }
    return { ok: true, payload: [{ id: "t1", kind: "hermes_work", title: "Draft Q3", status: "claimed" }] };
  });
  try {
    const result = await runJuniorTool("list_pending_work", "{}");
    assert.match(result, /1 thing waiting/);
  } finally {
    stub.restore();
  }
});

test("runJuniorTool create_task posts kind/title/instructions as the detail", async () => {
  const stub = stubFetch(() => ({
    ok: true,
    payload: { id: "t9", kind: "hermes_work", title: "Draft the Q3 summary" },
  }));
  try {
    const result = await runJuniorTool(
      "create_task",
      '{"kind":"hermes_work","title":"Draft the Q3 summary","instructions":"Summarize Q3 in one page."}',
    );
    const post = stub.calls.find((call) => call.init?.method === "POST");
    assert.ok(post, "create_task must POST");
    const body = JSON.parse(String(post!.init!.body));
    assert.equal(body.kind, "hermes_work");
    assert.equal(body.title, "Draft the Q3 summary");
    assert.equal(body.detail, "Summarize Q3 in one page.");
    assert.match(result, /Queued it as a hermes_work task/);
  } finally {
    stub.restore();
  }
});

test("runJuniorTool read_email maps the inbox payload to voice", async () => {
  const stub = stubFetch(() => ({
    ok: true,
    payload: [
      { id: "M1", from_address: "Jennifer <j@x.com>", subject: "Lunch Thursday", preview: "Free?", unread: true },
    ],
  }));
  try {
    const result = await runJuniorTool("read_email", '{"unread_only":true}');
    assert.match(result, /unread, from Jennifer <j@x.com> — "Lunch Thursday": Free\?/);
    const call = stub.calls[0];
    assert.match(call.url, /unread_only=true/);
    assert.match(call.url, /folder=inbox/);
  } finally {
    stub.restore();
  }
});

test("runJuniorTool draft_email posts a draft and the result says it is NOT sent", async () => {
  const stub = stubFetch(() => ({
    ok: true,
    payload: { id: "D1", to: "j@x.com", subject: "Re: Lunch" },
  }));
  try {
    const result = await runJuniorTool(
      "draft_email",
      '{"to":"j@x.com","subject":"Re: Lunch","body":"Thursday works.","reply_to":"M1"}',
    );
    const post = stub.calls.find((call) => call.init?.method === "POST");
    assert.ok(post);
    const body = JSON.parse(String(post!.init!.body));
    assert.equal(body.to, "j@x.com");
    assert.equal(body.reply_to_message_id, "M1");
    assert.match(result, /NOT sent/);
  } finally {
    stub.restore();
  }
});

test("runJuniorTool read_email_message returns the full body for reading aloud", async () => {
  const body = "Dear Steve, ".repeat(400); // ~4.8k chars — a full email
  const stub = stubFetch(() => ({
    ok: true,
    payload: { id: "M1", from_address: "j@x.com", subject: "Long note", body },
  }));
  try {
    const result = await runJuniorTool("read_email_message", '{"message_id":"M1"}');
    assert.ok(result.includes(body), "the full body must be returned for read-aloud");
    assert.ok(!result.includes("[excerpt"), "a body under the cap is complete");
  } finally {
    stub.restore();
  }
});

test("runJuniorTool list_feeds maps the feeds response with truncation", async () => {
  const longDescription = "D".repeat(600);
  const stub = stubFetch(() => ({
    ok: true,
    payload: [
      {
        id: "feed-1",
        title: "Newsmax",
        url: "https://newsmax.com/rss",
        description: longDescription,
        is_active: true,
        last_error: null,
      },
      { id: "feed-2", title: "Fox News", url: "https://foxnews.com/rss", description: null, is_active: false, last_error: "timeout" },
    ],
  }));
  try {
    const result = await runJuniorTool("list_feeds", "{}");
    assert.ok(stub.calls.some((call) => call.url.includes("/api/v1/feeds")), "list_feeds must GET /api/v1/feeds");
    assert.match(result, /You follow 2 feeds/);
    assert.match(result, /"Newsmax" \(https:\/\/newsmax\.com\/rss\)/);
    assert.match(result, /"Fox News" \(https:\/\/foxnews\.com\/rss\) \[paused\] \[last refresh failed\]/);
    // Descriptions are truncated so the spoken list stays short.
    assert.ok(!result.includes("D".repeat(600)), "descriptions must be truncated");
    assert.ok(result.includes("D".repeat(240)));
  } finally {
    stub.restore();
  }
});

test("runJuniorTool search_articles maps q/feed/saved_only onto the query string", async () => {
  const stub = stubFetch((url) => {
    if (url.includes("/api/v1/feeds")) {
      return { ok: true, payload: [{ id: "feed-1", title: "Newsmax", url: "https://newsmax.com/rss" }] };
    }
    // The articles route returns a Page envelope.
    return {
      ok: true,
      payload: {
        items: [
          {
            id: "art-1",
            title: "Markets rally",
            feed_title: "Newsmax",
            url: "https://newsmax.com/a1",
            summary: "S".repeat(600),
            is_saved: true,
            is_read: false,
          },
        ],
        total: 1,
        limit: 20,
        offset: 0,
      },
    };
  });
  try {
    const result = await runJuniorTool(
      "search_articles",
      '{"query":"markets","feed":"Newsmax","saved_only":true,"limit":5}',
    );
    const articlesCall = stub.calls.find((call) => call.url.includes("/api/v1/articles"));
    assert.ok(articlesCall, "search_articles must GET /api/v1/articles");
    const url = articlesCall!.url;
    assert.match(url, /q=markets/, "the free-text query maps onto q");
    assert.match(url, /feed_id=feed-1/, "the feed TITLE resolves to feed_id via list_feeds");
    assert.match(url, /saved=true/, "saved_only maps onto saved");
    assert.match(url, /limit=5/, "limit maps onto limit");
    assert.match(result, /"Markets rally" from Newsmax/);
    assert.match(result, /\[saved\]/);
    assert.match(result, /\(id: art-1\)/);
    assert.ok(!result.includes("S".repeat(600)), "summaries must be truncated");
    assert.ok(result.includes("S".repeat(500)));
  } finally {
    stub.restore();
  }
});

test("runJuniorTool search_articles speaks a helpful error for an unknown feed title", async () => {
  const stub = stubFetch((url) => {
    if (url.includes("/api/v1/feeds")) {
      return { ok: true, payload: [{ id: "feed-1", title: "Newsmax", url: "https://newsmax.com/rss" }] };
    }
    return { ok: true, payload: { items: [], total: 0, limit: 20, offset: 0 } };
  });
  try {
    const result = await runJuniorTool("search_articles", '{"feed":"Medium"}');
    assert.match(result, /don't have a feed called "Medium"/);
    assert.ok(!stub.calls.some((call) => call.url.includes("/api/v1/articles")), "no article search without a feed");
  } finally {
    stub.restore();
  }
});

test("runJuniorTool read_article returns the full text and continues by offset", async () => {
  const text = "a".repeat(DOC_READ_CHARS + 500);
  const stub = stubFetch(() => ({
    ok: true,
    payload: {
      id: "art-1",
      title: "Long Newsmax piece",
      feed_title: "Newsmax",
      url: "https://newsmax.com/a1",
      summary: "A long piece.",
      content_text: text,
    },
  }));
  try {
    const result = await runJuniorTool("read_article", '{"id":"art-1"}');
    assert.ok(stub.calls.some((call) => call.url.includes("/api/v1/articles/art-1")));
    assert.match(result, /"Long Newsmax piece" from Newsmax/);
    assert.match(result, /Summary: A long piece\./);
    // The first chunk is exactly the read cap and announces the continuation —
    // the same speakable marker get_document uses.
    assert.ok(result.includes("[excerpt"), "an oversized article must carry the continuation marker");
    assert.ok(result.includes(DOC_READ_CHARS.toLocaleString("en-US")));
    const firstText = result
      .slice(result.indexOf("Text: ") + "Text: ".length)
      .replace(/ \[excerpt[^\]]*\]$/, "");
    assert.equal(firstText.length, DOC_READ_CHARS, "the first chunk is exactly the read cap");
    assert.equal(firstText, text.slice(0, DOC_READ_CHARS));
  } finally {
    stub.restore();
  }

  const stub2 = stubFetch(() => ({
    ok: true,
    payload: { id: "art-1", title: "Long Newsmax piece", feed_title: "Newsmax", content_text: text },
  }));
  try {
    const result = await runJuniorTool("read_article", `{"id":"art-1","offset":${DOC_READ_CHARS}}`);
    const tail = result.slice(result.indexOf("Text: ") + "Text: ".length);
    assert.equal(tail, text.slice(DOC_READ_CHARS), "the continuation chunk holds exactly the tail");
    assert.ok(!result.includes("[excerpt"), "the final chunk needs no continuation marker");
  } finally {
    stub2.restore();
  }
});

test("runJuniorTool list_drafts and read_document_file hit their endpoints", async () => {
  const stub = stubFetch((url) => {
    if (url.includes("/files/")) {
      return { ok: true, payload: { filename: "chapter.docx", text: "Chapter one body." } };
    }
    return { ok: true, payload: [] };
  });
  try {
    assert.match(await runJuniorTool("list_drafts", "{}"), /No drafts waiting/);
    const fileResult = await runJuniorTool("read_document_file", '{"slug":"school","file_id":"f1"}');
    assert.match(fileResult, /Text: Chapter one body\./);
    assert.ok(stub.calls.some((call) => call.url.includes("/documents/school/files/f1/text")));
  } finally {
    stub.restore();
  }
});

/* ── Instructions ── */

test("JUNIOR_TALK_INSTRUCTIONS carves out read-aloud from the short-reply default", () => {
  // The short-reply default is still there…
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /one or two sentences unless asked for more/);
  // …and reading aloud is explicitly the "asked for more" case.
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /READ something/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /read it aloud in full/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /do NOT summarize/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /Summarize ONLY when he asks/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /want me to keep reading/);
});

test("JUNIOR_TALK_INSTRUCTIONS separates feed tools from library tools", () => {
  // The two systems must be named apart so the model picks the right one.
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /RSS FEEDS/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /LIBRARY documents/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /list_feeds/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /search_articles/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /read_article/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /'my article' or 'my feed', prefer the feed tools/);
});

test("JUNIOR_TALK_INSTRUCTIONS names every tool and the never-send rule", () => {
  for (const name of JUNIOR_TOOL_NAMES) {
    assert.ok(
      JUNIOR_TALK_INSTRUCTIONS.includes(name),
      `instructions must mention ${name}`,
    );
  }
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /NEVER send email/);
  assert.match(JUNIOR_TALK_INSTRUCTIONS, /web_search/);
});
