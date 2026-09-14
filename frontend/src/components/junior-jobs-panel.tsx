"use client";

import { useCallback, useEffect, useState, type Ref } from "react";
import { LoaderCircle, Pause, Play, Plus, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { DestinationSelect, FolderSelect } from "@/components/destination-controls";
import { ApiError, api, type JuniorJob } from "@/lib/api";
import type { CustomNoteShelf, FilingDestination } from "@/lib/custom-note-shelves";
import type { Folder } from "@/lib/types";

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

export function JuniorJobsPanel({
  conversationId,
  articleId,
  customShelves,
  onRanConversation,
  railRef,
}: {
  conversationId: string | null;
  articleId: string | null;
  customShelves: CustomNoteShelf[];
  onRanConversation: (conversationId: string) => void;
  railRef?: Ref<HTMLElement | null>;
}) {
  const [jobs, setJobs] = useState<JuniorJob[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [creating, setCreating] = useState(false);
  const [title, setTitle] = useState("");
  const [prompt, setPrompt] = useState("");
  const [cron, setCron] = useState("0 8 * * *");
  const [xhigh, setXhigh] = useState(false);
  const [saveNote, setSaveNote] = useState(false);
  const [shelf, setShelf] = useState<FilingDestination>("notes");
  const [folderId, setFolderId] = useState<string | null>(null);
  const [includeArticle, setIncludeArticle] = useState(false);
  const [folders, setFolders] = useState<Folder[]>([]);

  const loadJobs = useCallback(async () => {
    setLoading(true);
    try {
      const payload = await api.juniorJobs();
      setJobs(payload.items || []);
    } catch (error) {
      toast.error(error instanceof ApiError ? error.message : "Could not load Junior jobs.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadJobs();
  }, [loadJobs]);

  useEffect(() => {
    if (!saveNote) return;
    void api
      .folders(shelf)
      .then(setFolders)
      .catch(() => setFolders([]));
  }, [saveNote, shelf]);

  async function createJob() {
    if (!title.trim() || !prompt.trim()) {
      toast.error("Give the job a title and a prompt.");
      return;
    }
    setBusy(true);
    try {
      const saved = await api.createJuniorJob({
        title: title.trim(),
        prompt: prompt.trim(),
        cron,
        timezone: "America/New_York",
        conversation_id: conversationId,
        include_article_id: includeArticle ? articleId : null,
        shelf: saveNote ? shelf : null,
        folder_id: saveNote ? folderId : null,
        model: "grok-4.6",
        reasoning: "low",
        xhigh,
        enabled: true,
      });
      setJobs((current) => [saved, ...current]);
      setCreating(false);
      setTitle("");
      setPrompt("");
      toast.success("Job saved");
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not save that job.");
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
      toast.error(error instanceof Error ? error.message : "Could not update that job.");
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
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not delete that job.");
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
      toast.error(error instanceof Error ? error.message : "Could not run that job.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <aside ref={railRef} className="flex w-56 shrink-0 flex-col overflow-hidden border-r bg-muted/15">
      <div className="flex shrink-0 items-center justify-between gap-1 border-b p-2">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Jobs</p>
        <Button size="xs" variant="outline" onClick={() => setCreating((open) => !open)}>
          <Plus className="size-3" />
          New
        </Button>
      </div>
      {creating ? (
        <div className="shrink-0 space-y-2 border-b p-2">
          <Input value={title} onChange={(event) => setTitle(event.target.value)} placeholder="Title" className="h-7 text-xs" />
          <Textarea
            value={prompt}
            onChange={(event) => setPrompt(event.target.value)}
            placeholder="Prompt Junior will send"
            className="min-h-20 text-xs"
          />
          <select
            className="h-7 w-full rounded-md border bg-background px-2 text-xs"
            value={PRESETS.some((item) => item.cron === cron) ? cron : "custom"}
            onChange={(event) => {
              if (event.target.value !== "custom") setCron(event.target.value);
            }}
          >
            {PRESETS.map((item) => (
              <option key={item.cron} value={item.cron}>
                {item.label}
              </option>
            ))}
            <option value="custom">Custom cron</option>
          </select>
          <Input value={cron} onChange={(event) => setCron(event.target.value)} className="h-7 font-mono text-[11px]" />
          <label className="flex items-center gap-1.5 text-[11px]">
            <input type="checkbox" checked={xhigh} onChange={(event) => setXhigh(event.target.checked)} />
            xhigh (default is grok-4.6 · low)
          </label>
          <label className="flex items-center gap-1.5 text-[11px]">
            <input
              type="checkbox"
              checked={includeArticle}
              disabled={!articleId}
              onChange={(event) => setIncludeArticle(event.target.checked)}
            />
            Include open article
          </label>
          <label className="flex items-center gap-1.5 text-[11px]">
            <input type="checkbox" checked={saveNote} onChange={(event) => setSaveNote(event.target.checked)} />
            Also save as a note
          </label>
          {saveNote ? (
            <div className="flex flex-col gap-1">
              <DestinationSelect
                value={shelf}
                onChange={(next) => {
                  if (!next) return;
                  setShelf(next);
                  setFolderId(null);
                }}
                customShelves={customShelves}
                className="text-[11px]"
              />
              <FolderSelect
                shelf={shelf}
                folders={folders}
                value={folderId}
                onChange={setFolderId}
                onCreateFolder={() => undefined}
                className="text-[11px]"
              />
            </div>
          ) : null}
          <Button size="xs" disabled={busy} onClick={() => void createJob()}>
            Save job
          </Button>
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
                {job.last_status ? ` · ${job.last_status}` : ""}
              </p>
              <div className="mt-1 flex flex-wrap gap-1">
                <Button size="xs" variant="outline" disabled={busy} onClick={() => void runNow(job)}>
                  <Play className="size-3" />
                  Run now
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
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
