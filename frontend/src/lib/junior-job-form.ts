import type { JuniorJob } from "@/lib/api";
import type { FilingDestination } from "@/lib/custom-note-shelves";

export const JOB_TIMEZONES = [
  "America/New_York",
  "America/Chicago",
  "America/Denver",
  "America/Los_Angeles",
  "America/Phoenix",
  "UTC",
] as const;

export type JuniorJobDraft = {
  title: string;
  prompt: string;
  cron: string;
  timezone: string;
  xhigh: boolean;
  webSearch: boolean;
  saveNote: boolean;
  shelf: FilingDestination;
  folderId: string | null;
  includeArticle: boolean;
  enabled: boolean;
};

export function emptyJobDraft(): JuniorJobDraft {
  return {
    title: "",
    prompt: "",
    cron: "0 8 * * *",
    timezone: "America/New_York",
    xhigh: false,
    webSearch: false,
    saveNote: false,
    shelf: "notes",
    folderId: null,
    includeArticle: false,
    enabled: true,
  };
}

export function draftFromJob(job: JuniorJob): JuniorJobDraft {
  return {
    title: job.title || "",
    prompt: job.prompt || "",
    cron: job.cron || "0 8 * * *",
    timezone: job.timezone || "America/New_York",
    xhigh: Boolean(job.xhigh),
    webSearch: Boolean(job.web_search),
    saveNote: Boolean(job.shelf),
    shelf: (job.shelf as FilingDestination) || "notes",
    folderId: job.folder_id,
    includeArticle: Boolean(job.include_article_id),
    enabled: job.enabled !== false,
  };
}

export function jobWritePayload(
  draft: JuniorJobDraft,
  options?: { articleId?: string | null; existingIncludeId?: string | null },
): {
  title: string;
  prompt: string;
  cron: string;
  timezone: string;
  include_article_id: string | null;
  shelf: string | null;
  folder_id: string | null;
  model: "grok-4.6";
  reasoning: "low";
  xhigh: boolean;
  web_search: boolean;
  enabled: boolean;
} {
  const articleId = options?.articleId || null;
  const existingIncludeId = options?.existingIncludeId || null;
  let includeId: string | null = null;
  if (draft.includeArticle) {
    includeId = articleId || existingIncludeId;
  }
  return {
    title: draft.title.trim(),
    prompt: draft.prompt.trim(),
    cron: draft.cron.trim(),
    timezone: draft.timezone.trim() || "America/New_York",
    include_article_id: includeId,
    shelf: draft.saveNote ? draft.shelf : null,
    folder_id: draft.saveNote ? draft.folderId : null,
    model: "grok-4.6",
    reasoning: "low",
    xhigh: draft.xhigh,
    web_search: draft.webSearch,
    enabled: draft.enabled,
  };
}
