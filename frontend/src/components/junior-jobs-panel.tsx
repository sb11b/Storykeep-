"use client";

import { useCallback, useEffect, useState, type Ref } from "react";
import { ChevronLeft, LoaderCircle, Pause, Pencil, Play, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { DestinationSelect, FolderSelect } from "@/components/destination-controls";
import { api, type JuniorJob } from "@/lib/api";
import { toastActionError } from "@/lib/toast-message";
import type { CustomNoteShelf } from "@/lib/custom-note-shelves";
import type { Folder } from "@/lib/types";
import {
  JOB_TIMEZONES,
  draftFromJob,
  emptyJobDraft,
  jobWritePayload,
  type JuniorJobDraft,
} from "@/lib/junior-job-form";

const PRESETS: { label: string; cron: string }[] = [
  { label: "Daily 8:00", cron: "0 8 * * *" },
  { label: "Weekdays 8:00", cron: "0 8 * * 1-5" },
  { label: "Weekdays 16:30", cron: "30 16 * * 1-5" },
  { label: "Sunday 10:00", cron: "0 10 * * 0" },
];

function formatWhen(iso: string | null) {
  if (!iso) return "never";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "never";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

function JobForm({
  draft,
  onChange,
  articleId,
  customShelves,
  folders,
  busy,
  saveLabel,
  onSave,
  onCancel,
}: {
  draft: JuniorJobDraft;
  onChange: (next: JuniorJobDraft) => void;
  articleId: string | null;
  customShelves: CustomNoteShelf[];
  folders: Folder[];
  busy: boolean;
  saveLabel: string;
  onSave: () => void;
  onCancel: () => void;
}) {
  const set = (patch: Partial<JuniorJobDraft>) => onChange({ ...draft, ...patch });
  const zones = JOB_TIMEZONES.includes(draft.timezone as (typeof JOB_TIMEZONES)[number])
    ? [...JOB_TIMEZONES]
    : [draft.timezone, ...JOB_TIMEZONES];

  return (
    <div className="space-y-2">
      <Input
        value={draft.title}
        onChange={(event) => set({ title: event.target.value })}
        placeholder="Title"
        className="h-7 text-xs"
        aria-label="Job title"
      />
      <Textarea
        value={draft.prompt}
        onChange={(event) => set({ prompt: event.target.value })}
        placeholder="Prompt Junior will send"
        className="min-h-20 text-xs"
        aria-label="Job prompt"
      />
      <select
        className="h-7 w-full rounded-md border bg-background px-2 text-xs"
        value={PRESETS.some((item) => item.cron === draft.cron) ? draft.cron : "custom"}
        onChange={(event) => {
          if (event.target.value !== "custom") set({ cron: event.target.value });
        }}
        aria-label="Schedule preset"
      >
        {PRESETS.map((item) => (
          <option key={item.cron} value={item.cron}>
            {item.label}
          </option>
        ))}
        <option value="custom">Custom cron</option>
      </select>
      <Input
        value={draft.cron}
        onChange={(event) => set({ cron: event.target.value })}
        className="h-7 font-mono text-[11px]"
        aria-label="Cron schedule"
      />
      <select
        className="h-7 w-full rounded-md border bg-background px-2 text-xs"
        value={draft.timezone}
        onChange={(event) => set({ timezone: event.target.value })}
        aria-label="Timezone"
      >
        {zones.map((zone) => (
          <option key={zone} value={zone}>
            {zone}
          </option>
        ))}
      </select>
      <label className="flex items-center gap-1.5 text-[11px]">
        <input type="checkbox" checked={draft.enabled} onChange={(event) => set({ enabled: event.target.checked })} />
        Enabled
      </label>
      <label className="flex items-center gap-1.5 text-[11px]">
        <input type="checkbox" checked={draft.xhigh} onChange={(event) => set({ xhigh: event.target.checked })} />
        xhigh (default is grok-4.6 · low)
      </label>
      <label className="flex items-center gap-1.5 text-[11px]">
        <input type="checkbox" checked={draft.webSearch} onChange={(event) => set({ webSearch: event.target.checked })} />
        Allow web search
      </label>
      <label className="flex items-center gap-1.5 text-[11px]">
        <input
          type="checkbox"
          checked={draft.includeArticle}
          disabled={!articleId && !draft.includeArticle}
          onChange={(event) => set({ includeArticle: event.target.checked })}
        />
        Include open article
      </label>
      <label className="flex items-center gap-1.5 text-[11px]">
        <input type="checkbox" checked={draft.saveNote} onChange={(event) => set({ saveNote: event.target.checked })} />
        Also save as a note
      </label>
      {draft.saveNote ? (
        <div className="flex flex-col gap-1">
          <DestinationSelect
            value={draft.shelf}
            onChange={(next) => {
              if (!next) return;
              set({ shelf: next, folderId: null });
            }}
            customShelves={customShelves}
            className="text-[11px]"
          />
          <FolderSelect
            shelf={draft.shelf}
            folders={folders}
            value={draft.folderId}
            onChange={(folderId) => set({ folderId })}
            onCreateFolder={() => undefined}
            className="text-[11px]"
          />
        </div>
      ) : null}
      <div className="flex flex-wrap gap-1">
        <Button type="button" size="xs" disabled={busy} onClick={onSave}>
          {saveLabel}
        </Button>
        <Button type="button" size="xs" variant="outline" disabled={busy} onClick={onCancel}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

export function JuniorJobsPanel({
  conversationId,
  articleId,
  customShelves,
  onRanConversation,
  railRef,
  onHide,
}: {
  conversationId: string | null;
  articleId: string | null;
  customShelves: CustomNoteShelf[];
  onRanConversation: (conversationId: string) => void;
  railRef?: Ref<HTMLElement | null>;
  onHide?: () => void;
}) {
  const [jobs, setJobs] = useState<JuniorJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [draft, setDraft] = useState<JuniorJobDraft>(emptyJobDraft);
  const [folders, setFolders] = useState<Folder[]>([]);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await api.juniorJobs();
      setJobs(payload.items || []);
    } catch (error) {
      toastActionError(error, "load Junior jobs", "Could not load Junior jobs.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    if (!draft.saveNote) return;
    void api
      .folders(draft.shelf)
      .then(setFolders)
      .catch(() => setFolders([]));
  }, [draft.saveNote, draft.shelf]);

  function openCreate() {
    setEditingId(null);
    setDraft(emptyJobDraft());
    setCreating((open) => !open);
  }

  function openEdit(job: JuniorJob) {
    setCreating(false);
    setEditingId(job.id);
    setDraft(draftFromJob(job));
  }

  function cancelForm() {
    setCreating(false);
    setEditingId(null);
    setDraft(emptyJobDraft());
  }

  async function saveForm() {
    if (!draft.title.trim() || !draft.prompt.trim()) {
      toast.error("Give the job a title and a prompt.");
      return;
    }
    const editing = jobs.find((job) => job.id === editingId) || null;
    const body = jobWritePayload(draft, {
      articleId,
      existingIncludeId: editing?.include_article_id || null,
    });
    setBusy(true);
    try {
      if (editingId) {
        const saved = await api.patchJuniorJob(editingId, body);
        setJobs((current) => current.map((item) => (item.id === saved.id ? saved : item)));
        toast.success("Job updated");
      } else {
        const saved = await api.createJuniorJob({ ...body, conversation_id: conversationId });
        setJobs((current) => [saved, ...current]);
        toast.success("Job saved");
      }
      cancelForm();
    } catch (error) {
      toastActionError(error, "save that job", "Could not save that job.");
    } finally {
      setBusy(false);
    }
  }

  async function toggleJob(job: JuniorJob) {
    setBusy(true);
    try {
      const saved = await api.patchJuniorJob(job.id, { enabled: !job.enabled });
      setJobs((current) => current.map((item) => (item.id === saved.id ? saved : item)));
    } catch (error) {
      toastActionError(error, "update that job", "Could not update that job.");
    } finally {
      setBusy(false);
    }
  }

  async function removeJob(job: JuniorJob) {
    if (!window.confirm(`Delete “${job.title}”?`)) return;
    setBusy(true);
    try {
      await api.deleteJuniorJob(job.id);
      setJobs((current) => current.filter((item) => item.id !== job.id));
      if (editingId === job.id) cancelForm();
    } catch (error) {
      toastActionError(error, "delete that job", "Could not delete that job.");
    } finally {
      setBusy(false);
    }
  }

  async function runNow(job: JuniorJob) {
    setBusy(true);
    try {
      const result = await api.runJuniorJob(job.id);
      setJobs((current) => current.map((item) => (item.id === result.job.id ? result.job : item)));
      if (result.conversation_id) onRanConversation(result.conversation_id);
      toast.success(result.job.last_status === "ok" ? "Job finished — check the thread" : "Job ran with an error");
    } catch (error) {
      toastActionError(error, "run that job", "Could not run that job.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside ref={railRef} className="flex w-56 shrink-0 flex-col overflow-hidden border-r bg-muted/15">
      <div className="flex shrink-0 items-center justify-between gap-1 border-b p-2">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Jobs</p>
        <div className="flex items-center gap-1">
          {onHide ? (
            <Button
              type="button"
              size="icon-xs"
              variant="ghost"
              aria-label="Hide Jobs"
              aria-expanded={true}
              title="Hide Jobs"
              onClick={onHide}
            >
              <ChevronLeft className="size-3.5" />
            </Button>
          ) : null}
          <Button size="xs" variant="outline" onClick={openCreate}>
            <Plus className="size-3" />
            New
          </Button>
        </div>
      </div>
      {creating ? (
        <div className="shrink-0 space-y-2 border-b p-2">
          <JobForm
            draft={draft}
            onChange={setDraft}
            articleId={articleId}
            customShelves={customShelves}
            folders={folders}
            busy={busy}
            saveLabel="Save job"
            onSave={() => void saveForm()}
            onCancel={cancelForm}
          />
        </div>
      ) : null}
      <div className="min-h-0 flex-1 overflow-y-auto p-1">
        {loading ? (
          <p className="flex items-center gap-1 px-2 py-2 text-[11px] text-muted-foreground">
            <LoaderCircle className="size-3 animate-spin" />
            Loading…
          </p>
        ) : jobs.length === 0 ? (
          <p className="px-2 py-2 text-[11px] text-muted-foreground">No jobs yet. New → save a prompt on a cron.</p>
        ) : (
          jobs.map((job) => (
            <div key={job.id} className="rounded-md px-2 py-1.5 hover:bg-accent/40">
              <p className="text-[11px] font-medium leading-snug">{job.title}</p>
              <p className="text-[10px] text-muted-foreground">
                {job.enabled ? "On" : "Paused"} · {job.cron} · {formatWhen(job.last_run_at)}
                {job.web_search ? " · search" : ""}
                {job.last_status ? ` · ${job.last_status}` : ""}
              </p>
              {editingId === job.id ? (
                <div className="mt-1.5 rounded-md border bg-background p-1.5">
                  <JobForm
                    draft={draft}
                    onChange={setDraft}
                    articleId={articleId}
                    customShelves={customShelves}
                    folders={folders}
                    busy={busy}
                    saveLabel="Save"
                    onSave={() => void saveForm()}
                    onCancel={cancelForm}
                  />
                </div>
              ) : (
                <div className="mt-1 flex flex-wrap gap-1">
                  <Button size="xs" variant="outline" disabled={busy} onClick={() => void runNow(job)}>
                    <Play className="size-3" />
                    Run now
                  </Button>
                  <Button size="xs" variant="outline" disabled={busy} onClick={() => openEdit(job)}>
                    <Pencil className="size-3" />
                    Edit
                  </Button>
                  <Button size="xs" variant="ghost" disabled={busy} onClick={() => void toggleJob(job)}>
                    <Pause className="size-3" />
                    {job.enabled ? "Pause" : "Resume"}
                  </Button>
                  <Button size="xs" variant="ghost" disabled={busy} onClick={() => void removeJob(job)}>
                    <Trash2 className="size-3" />
                    Delete
                  </Button>
                </div>
              )}
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
