import assert from "node:assert/strict";
import test from "node:test";
import { draftFromJob, emptyJobDraft, jobWritePayload } from "@/lib/junior-job-form";
import type { JuniorJob } from "@/lib/api";

const sample: JuniorJob = {
  id: "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa",
  title: "Top Five",
  prompt: "Top five news",
  cron: "0 8 * * 1-5",
  timezone: "America/New_York",
  conversation_id: "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb",
  shelf: null,
  folder_id: null,
  include_article_id: null,
  model: "grok-4.6",
  reasoning: "low",
  xhigh: false,
  web_search: false,
  enabled: true,
  last_run_at: null,
  last_status: "ok",
  created_at: null,
  updated_at: null,
};

test("edit payload keeps the same fields and new prompt", () => {
  const draft = draftFromJob(sample);
  draft.prompt = "Unread Fox only";
  const body = jobWritePayload(draft);
  assert.equal(body.title, "Top Five");
  assert.equal(body.prompt, "Unread Fox only");
  assert.equal(body.cron, "0 8 * * 1-5");
  assert.equal(body.web_search, false);
  assert.equal(body.xhigh, false);
  assert.equal(body.enabled, true);
  assert.equal(body.shelf, null);
});

test("new draft defaults search off and enabled on", () => {
  const draft = emptyJobDraft();
  assert.equal(draft.webSearch, false);
  assert.equal(draft.enabled, true);
  assert.equal(draft.timezone, "America/New_York");
});
