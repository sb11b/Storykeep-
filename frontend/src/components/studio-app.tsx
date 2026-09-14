"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import {
  Bot,
  FileCode,
  FolderTree,
  LoaderCircle,
  Play,
  Plus,
  Save,
  Trash2,
  WandSparkles,
} from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import {
  api,
  ApiError,
  type StudioAgentReply,
  type StudioAutomation,
  type StudioFile,
  type StudioRun,
  type StudioTemplate,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type Tab = "automations" | "build";

const EMPTY_AUTOMATION: Omit<StudioAutomation, "id" | "next_run_at" | "last_run_at"> = {
  title: "",
  instruction: "",
  trigger: "schedule",
  schedule: "daily",
  hour: 8,
  minute: 0,
  weekday: 0,
  monthday: 1,
  timezone: "America/New_York",
  notify: "app",
  email_from: null,
  email_to: null,
  email_subject: null,
  enabled: true,
  include_unread: false,
};

function formatWhen(iso: string | null) {
  if (!iso) return "—";
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return "—";
  return date.toLocaleString(undefined, { month: "short", day: "numeric", hour: "numeric", minute: "2-digit" });
}

export function StudioApp() {
  const router = useRouter();
  const [tab, setTab] = useState<Tab>("automations");
  const [templates, setTemplates] = useState<StudioTemplate[]>([]);
  const [automations, setAutomations] = useState<StudioAutomation[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [draft, setDraft] = useState(EMPTY_AUTOMATION);
  const [runs, setRuns] = useState<StudioRun[]>([]);
  const [emailSample, setEmailSample] = useState("Vendor Acme billed $42 due Friday.\nPlease review.");
  const [files, setFiles] = useState<StudioFile[]>([]);
  const [activePath, setActivePath] = useState<string | null>(null);
  const [editor, setEditor] = useState("");
  const [dirty, setDirty] = useState(false);
  const [agentMode, setAgentMode] = useState<"plan" | "build">("plan");
  const [prompt, setPrompt] = useState("");
  const [agentReply, setAgentReply] = useState<StudioAgentReply | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const selected = useMemo(
    () => automations.find((item) => item.id === selectedId) || null,
    [automations, selectedId],
  );
  const activeFile = files.find((item) => item.path === activePath) || null;

  const loadStudio = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [tpl, autos, workspace] = await Promise.all([
        api.studioTemplates(),
        api.studioAutomations(),
        api.studioWorkspace(),
      ]);
      setTemplates(tpl.items || []);
      setAutomations(autos.items || []);
      const ws = workspace.items || [];
      setFiles(ws);
      setActivePath((cur) => (cur && ws.some((file) => file.path === cur) ? cur : ws[0]?.path ?? null));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not open Grok Studio.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStudio();
  }, [loadStudio]);

  useEffect(() => {
    if (!selectedId) {
      setRuns([]);
      return;
    }
    void api
      .studioRuns(selectedId)
      .then((payload) => setRuns(payload.items || []))
      .catch(() => setRuns([]));
  }, [selectedId]);

  useEffect(() => {
    if (!activeFile || dirty) return;
    setEditor(activeFile.content);
  }, [activeFile, dirty]);

  function applyTemplate(item: StudioTemplate) {
    setSelectedId(null);
    setDraft({
      ...EMPTY_AUTOMATION,
      title: item.title,
      instruction: item.instruction,
      trigger: item.trigger,
      schedule: item.schedule,
      hour: item.hour ?? 8,
      minute: item.minute ?? 0,
      weekday: item.weekday ?? 0,
      include_unread: Boolean(item.include_unread),
      notify: item.notify || "app",
      email_subject: item.email_subject || null,
    });
    setTab("automations");
  }

  function openAutomation(item: StudioAutomation) {
    setSelectedId(item.id);
    setDraft({ ...item });
  }

  async function saveAutomation() {
    if (!draft.title.trim() || !draft.instruction.trim()) {
      toast.error("Give the job a title and instructions.");
      return;
    }
    setBusy(true);
    try {
      const body = {
        ...draft,
        title: draft.title.trim(),
        instruction: draft.instruction.trim(),
      };
      const saved = selectedId
        ? await api.studioPatchAutomation(selectedId, body)
        : await api.studioCreateAutomation(body);
      setAutomations((current) => {
        const rest = current.filter((item) => item.id !== saved.id);
        return [saved, ...rest];
      });
      setSelectedId(saved.id);
      setDraft({ ...saved });
      toast.success(selectedId ? "Automation updated" : "Automation saved");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save that automation.");
    } finally {
      setBusy(false);
    }
  }

  async function runSelected(kind: "now" | "email") {
    if (!selectedId) {
      toast.error("Save the automation first.");
      return;
    }
    setBusy(true);
    try {
      const result =
        kind === "email"
          ? await api.studioFireEmail(selectedId, { subject: draft.email_subject || "Invoice", body: emailSample })
          : await api.studioRunNow(selectedId);
      setAutomations((current) => current.map((item) => (item.id === result.automation.id ? result.automation : item)));
      setRuns((current) => [result.run, ...current]);
      toast.success(result.run.status === "ok" ? "Run finished" : "Run failed");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not run that automation.");
    } finally {
      setBusy(false);
    }
  }

  async function removeAutomation() {
    if (!selectedId) return;
    if (!window.confirm("Delete this automation and its run history?")) return;
    setBusy(true);
    try {
      await api.studioDeleteAutomation(selectedId);
      setAutomations((current) => current.filter((item) => item.id !== selectedId));
      setSelectedId(null);
      setDraft(EMPTY_AUTOMATION);
      setRuns([]);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not delete that automation.");
    } finally {
      setBusy(false);
    }
  }

  async function saveFile() {
    if (!activePath) return;
    setBusy(true);
    try {
      const saved = await api.studioPutFile({ path: activePath, content: editor });
      setFiles((current) => current.map((item) => (item.path === saved.path ? saved : item)));
      setDirty(false);
      toast.success(`Saved ${saved.path}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save that file.");
    } finally {
      setBusy(false);
    }
  }

  async function addFile() {
    const path = window.prompt("New file path", "src/app.py");
    if (!path) return;
    setBusy(true);
    try {
      const saved = await api.studioPutFile({ path, content: "" });
      setFiles((current) => [...current.filter((item) => item.path !== saved.path), saved].sort((a, b) => a.path.localeCompare(b.path)));
      setActivePath(saved.path);
      setEditor("");
      setDirty(false);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not create that file.");
    } finally {
      setBusy(false);
    }
  }

  async function removeFile(path: string) {
    if (!window.confirm(`Delete ${path}?`)) return;
    setBusy(true);
    try {
      await api.studioDeleteFile(path);
      const next = files.filter((item) => item.path !== path);
      setFiles(next);
      if (activePath === path) {
        setActivePath(next[0]?.path ?? null);
        setEditor(next[0]?.content ?? "");
        setDirty(false);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not delete that file.");
    } finally {
      setBusy(false);
    }
  }

  async function runAgent() {
    const text = prompt.trim();
    if (!text) {
      toast.error("Tell Grok Build what to do.");
      return;
    }
    setBusy(true);
    setAgentReply(null);
    try {
      const reply = await api.studioAgent({ message: text, mode: agentMode });
      setAgentReply(reply);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Grok Build did not reply.");
    } finally {
      setBusy(false);
    }
  }

  async function applyPatches() {
    const patches = agentReply?.patches || [];
    if (!patches.length) {
      toast.error("No patches to apply.");
      return;
    }
    setBusy(true);
    try {
      const result = await api.studioApplyPatches(patches);
      const next = [...files];
      for (const saved of result.items) {
        const index = next.findIndex((item) => item.path === saved.path);
        if (index >= 0) next[index] = saved;
        else next.push(saved);
      }
      next.sort((a, b) => a.path.localeCompare(b.path));
      setFiles(next);
      const focus = result.items[0];
      if (focus) {
        setActivePath(focus.path);
        setEditor(focus.content);
        setDirty(false);
      }
      toast.success(`Applied ${result.items.length} file${result.items.length === 1 ? "" : "s"}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not apply those patches.");
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return (
      <div className="flex h-full items-center justify-center gap-2 text-sm text-muted-foreground">
        <LoaderCircle className="size-4 animate-spin" />
        Opening Grok Studio…
      </div>
    );
  }

  if (error) {
    return (
      <div className="mx-auto flex h-full max-w-md flex-col items-center justify-center gap-3 px-4 text-center">
        <p className="font-[family-name:var(--font-serif)] text-2xl">Studio is offline</p>
        <p className="text-sm text-muted-foreground">{error}</p>
        <Button onClick={() => void loadStudio()}>Try again</Button>
      </div>
    );
  }

  return (
    <div className="flex h-full min-h-0 flex-col overflow-hidden bg-[var(--storykeep-page-bg)]">
      <header className="flex shrink-0 flex-wrap items-center gap-2 border-b px-3 py-2">
        <Bot className="size-4" />
        <p className="font-[family-name:var(--font-serif)] text-lg">Grok Studio</p>
        <span className="text-xs text-muted-foreground">Automations + Build IDE</span>
        <div className="ml-auto flex flex-wrap gap-1">
          <Button size="sm" variant={tab === "automations" ? "default" : "outline"} onClick={() => setTab("automations")}>
            Automations
          </Button>
          <Button size="sm" variant={tab === "build" ? "default" : "outline"} onClick={() => setTab("build")}>
            Build IDE
          </Button>
          <Button size="sm" variant="ghost" onClick={() => router.push("/")}>
            Library
          </Button>
        </div>
      </header>

      {tab === "automations" ? (
        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[16rem_minmax(0,1fr)_20rem]">
          <aside className="min-h-0 overflow-y-auto border-b p-3 lg:border-b-0 lg:border-r">
            <p className="mb-2 text-[11px] uppercase tracking-wide text-muted-foreground">Templates</p>
            <div className="space-y-1">
              {templates.map((item) => (
                <button
                  key={item.id}
                  type="button"
                  className="w-full rounded-md border px-2 py-1.5 text-left text-xs hover:bg-muted/60"
                  onClick={() => applyTemplate(item)}
                >
                  <span className="font-medium">{item.title}</span>
                  <span className="mt-0.5 block text-[10px] text-muted-foreground">
                    {item.trigger === "email" ? "Email trigger" : item.schedule}
                  </span>
                </button>
              ))}
            </div>
            <div className="mt-4 flex items-center justify-between">
              <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Yours</p>
              <Button
                size="xs"
                variant="outline"
                onClick={() => {
                  setSelectedId(null);
                  setDraft(EMPTY_AUTOMATION);
                }}
              >
                <Plus className="size-3" />
                New
              </Button>
            </div>
            {automations.length === 0 ? (
              <p className="mt-2 text-xs text-muted-foreground">No jobs yet. Start from a template or write one.</p>
            ) : (
              <ul className="mt-2 space-y-1">
                {automations.map((item) => (
                  <li key={item.id}>
                    <button
                      type="button"
                      className={cn(
                        "w-full rounded-md px-2 py-1.5 text-left text-xs",
                        selectedId === item.id ? "bg-primary/10" : "hover:bg-muted/60",
                      )}
                      onClick={() => openAutomation(item)}
                    >
                      <span className="font-medium">{item.title}</span>
                      <span className="mt-0.5 block text-[10px] text-muted-foreground">
                        {item.enabled ? "On" : "Paused"} · next {formatWhen(item.next_run_at)}
                      </span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </aside>

          <section className="min-h-0 overflow-y-auto p-4">
            <div className="mx-auto max-w-2xl space-y-3">
              <Input
                value={draft.title}
                onChange={(event) => setDraft((current) => ({ ...current, title: event.target.value }))}
                placeholder="Job title"
              />
              <Textarea
                value={draft.instruction}
                onChange={(event) => setDraft((current) => ({ ...current, instruction: event.target.value }))}
                placeholder="Describe the job once. Grok runs it on the schedule or when a matching email arrives."
                className="min-h-36"
              />
              <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
                <label className="text-xs text-muted-foreground">
                  Trigger
                  <select
                    className="mt-1 h-8 w-full rounded-md border bg-background px-2 text-sm"
                    value={draft.trigger}
                    onChange={(event) => setDraft((current) => ({ ...current, trigger: event.target.value }))}
                  >
                    <option value="schedule">Schedule</option>
                    <option value="email">Email</option>
                  </select>
                </label>
                <label className="text-xs text-muted-foreground">
                  Repeat
                  <select
                    className="mt-1 h-8 w-full rounded-md border bg-background px-2 text-sm"
                    value={draft.schedule}
                    onChange={(event) => setDraft((current) => ({ ...current, schedule: event.target.value }))}
                  >
                    <option value="once">Once</option>
                    <option value="daily">Daily</option>
                    <option value="weekdays">Weekdays</option>
                    <option value="weekly">Weekly</option>
                    <option value="monthly">Monthly</option>
                    <option value="yearly">Yearly</option>
                  </select>
                </label>
                <label className="text-xs text-muted-foreground">
                  Hour
                  <Input
                    type="number"
                    className="mt-1 h-8"
                    value={draft.hour}
                    onChange={(event) => setDraft((current) => ({ ...current, hour: Number(event.target.value) }))}
                  />
                </label>
                <label className="text-xs text-muted-foreground">
                  Minute
                  <Input
                    type="number"
                    className="mt-1 h-8"
                    value={draft.minute}
                    onChange={(event) => setDraft((current) => ({ ...current, minute: Number(event.target.value) }))}
                  />
                </label>
              </div>
              {draft.schedule === "weekly" ? (
                <label className="text-xs text-muted-foreground">
                  Weekday
                  <select
                    className="mt-1 h-8 w-full max-w-xs rounded-md border bg-background px-2 text-sm"
                    value={draft.weekday}
                    onChange={(event) => setDraft((current) => ({ ...current, weekday: Number(event.target.value) }))}
                  >
                    <option value={0}>Monday</option>
                    <option value={1}>Tuesday</option>
                    <option value={2}>Wednesday</option>
                    <option value={3}>Thursday</option>
                    <option value={4}>Friday</option>
                    <option value={5}>Saturday</option>
                    <option value={6}>Sunday</option>
                  </select>
                </label>
              ) : null}
              {draft.schedule === "monthly" || draft.schedule === "yearly" ? (
                <label className="text-xs text-muted-foreground">
                  Day of month
                  <Input
                    type="number"
                    className="mt-1 h-8 max-w-xs"
                    min={1}
                    max={28}
                    value={draft.monthday}
                    onChange={(event) => setDraft((current) => ({ ...current, monthday: Number(event.target.value) }))}
                  />
                </label>
              ) : null}
              <label className="text-xs text-muted-foreground">
                Notify
                <select
                  className="mt-1 h-8 w-full max-w-xs rounded-md border bg-background px-2 text-sm"
                  value={draft.notify}
                  onChange={(event) => setDraft((current) => ({ ...current, notify: event.target.value }))}
                >
                  <option value="none">None</option>
                  <option value="app">In Studio history</option>
                  <option value="email">Email (stored, not sent)</option>
                  <option value="both">History + email (stored)</option>
                </select>
              </label>
              {draft.trigger === "email" ? (
                <Input
                  value={draft.email_subject || ""}
                  onChange={(event) => setDraft((current) => ({ ...current, email_subject: event.target.value }))}
                  placeholder="Subject contains (e.g. invoice)"
                />
              ) : null}
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.include_unread}
                  onChange={(event) => setDraft((current) => ({ ...current, include_unread: event.target.checked }))}
                />
                Attach unread StoryKeep titles
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={draft.enabled}
                  onChange={(event) => setDraft((current) => ({ ...current, enabled: event.target.checked }))}
                />
                Enabled
              </label>
              <div className="flex flex-wrap gap-2">
                <Button disabled={busy} onClick={() => void saveAutomation()}>
                  <Save className="size-3.5" />
                  Save
                </Button>
                <Button disabled={busy || !selectedId} variant="outline" onClick={() => void runSelected("now")}>
                  {busy ? <LoaderCircle className="size-3.5 animate-spin" /> : <Play className="size-3.5" />}
                  Run now
                </Button>
                {draft.trigger === "email" ? (
                  <Button disabled={busy || !selectedId} variant="outline" onClick={() => void runSelected("email")}>
                    Fire sample email
                  </Button>
                ) : null}
                <Button disabled={!selectedId} variant="ghost" onClick={() => void removeAutomation()}>
                  <Trash2 className="size-3.5" />
                  Delete
                </Button>
              </div>
              {draft.trigger === "email" ? (
                <Textarea
                  value={emailSample}
                  onChange={(event) => setEmailSample(event.target.value)}
                  className="min-h-24"
                  placeholder="Paste a sample email body to test the trigger."
                />
              ) : null}
            </div>
          </section>

          <aside className="min-h-0 overflow-y-auto border-t p-3 lg:border-l lg:border-t-0">
            <p className="mb-2 text-[11px] uppercase tracking-wide text-muted-foreground">Run history</p>
            {runs.length === 0 ? (
              <p className="text-xs text-muted-foreground">No runs yet. Save, then Run now.</p>
            ) : (
              <ul className="space-y-3">
                {runs.map((run) => (
                  <li key={run.id} className="rounded-md border p-2 text-xs">
                    <p className="font-medium">
                      {run.status === "ok" ? "Finished" : "Failed"} · {formatWhen(run.created_at)}
                    </p>
                    {run.model ? (
                      <p className="text-[10px] text-muted-foreground">
                        this turn · {run.model} · {run.reasoning || "low"}
                      </p>
                    ) : null}
                    <p className="mt-1 whitespace-pre-wrap text-foreground">{run.output}</p>
                  </li>
                ))}
              </ul>
            )}
          </aside>
        </div>
      ) : (
        <div className="grid min-h-0 flex-1 grid-cols-1 overflow-hidden lg:grid-cols-[14rem_minmax(0,1fr)_22rem]">
          <aside className="min-h-0 overflow-y-auto border-b p-3 lg:border-b-0 lg:border-r">
            <div className="mb-2 flex items-center justify-between">
              <p className="flex items-center gap-1 text-[11px] uppercase tracking-wide text-muted-foreground">
                <FolderTree className="size-3" />
                Files
              </p>
              <Button size="xs" variant="outline" onClick={() => void addFile()}>
                <Plus className="size-3" />
              </Button>
            </div>
            {files.length === 0 ? (
              <p className="text-xs text-muted-foreground">Workspace is empty.</p>
            ) : (
              <ul className="space-y-0.5">
                {files.map((item) => (
                  <li key={item.path} className="flex items-center gap-1">
                    <button
                      type="button"
                      className={cn(
                        "min-w-0 flex-1 truncate rounded px-2 py-1 text-left font-mono text-[11px]",
                        activePath === item.path ? "bg-primary/10" : "hover:bg-muted/60",
                      )}
                      onClick={() => {
                        if (dirty && !window.confirm("Discard unsaved edits?")) return;
                        setActivePath(item.path);
                        setEditor(item.content);
                        setDirty(false);
                      }}
                    >
                      {item.path}
                    </button>
                    <button type="button" className="text-muted-foreground hover:text-destructive" onClick={() => void removeFile(item.path)}>
                      <Trash2 className="size-3" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </aside>
          <section className="flex min-h-0 flex-col">
            <div className="flex shrink-0 items-center gap-2 border-b px-3 py-1.5 text-xs">
              <FileCode className="size-3.5" />
              <span className="font-mono">{activePath || "No file selected"}</span>
              {dirty ? <span className="text-muted-foreground">unsaved</span> : null}
              <Button size="xs" className="ml-auto" disabled={!activePath || busy} onClick={() => void saveFile()}>
                <Save className="size-3" />
                Save
              </Button>
            </div>
            {activePath ? (
              <textarea
                value={editor}
                onChange={(event) => {
                  setEditor(event.target.value);
                  setDirty(true);
                }}
                spellCheck={false}
                className="min-h-0 flex-1 resize-none bg-background p-3 font-mono text-xs outline-none"
              />
            ) : (
              <p className="p-6 text-sm text-muted-foreground">Open a file from the tree.</p>
            )}
          </section>
          <aside className="flex min-h-0 flex-col border-t lg:border-l lg:border-t-0">
            <div className="flex shrink-0 gap-1 border-b p-2">
              <Button size="xs" variant={agentMode === "plan" ? "default" : "outline"} onClick={() => setAgentMode("plan")}>
                Plan
              </Button>
              <Button size="xs" variant={agentMode === "build" ? "default" : "outline"} onClick={() => setAgentMode("build")}>
                Build
              </Button>
            </div>
            <div className="min-h-0 flex-1 overflow-y-auto p-3 text-sm">
              {!agentReply ? (
                <p className="text-xs text-muted-foreground">
                  Plan mode writes a step list. Approve it by switching to Build and sending the same task. Build returns file patches you can apply.
                </p>
              ) : (
                <div className="space-y-3">
                  <p className="text-[10px] text-muted-foreground">
                    this turn · {agentReply.model} · {agentReply.reasoning}
                  </p>
                  {agentReply.plan.length ? (
                    <ol className="list-decimal space-y-1 pl-4 text-xs">
                      {agentReply.plan.map((step) => (
                        <li key={step.id}>
                          <span className="font-medium">{step.title}</span>
                          {step.detail ? <span className="block text-muted-foreground">{step.detail}</span> : null}
                        </li>
                      ))}
                    </ol>
                  ) : (
                    <p className="whitespace-pre-wrap text-xs">{agentReply.text}</p>
                  )}
                  {agentReply.patches.length ? (
                    <div className="space-y-2">
                      {agentReply.patches.map((patch) => (
                        <div key={patch.path} className="rounded-md border">
                          <p className="border-b px-2 py-1 font-mono text-[10px]">{patch.path}</p>
                          <pre className="max-h-40 overflow-auto p-2 text-[10px]">{patch.content}</pre>
                        </div>
                      ))}
                      <Button size="sm" onClick={() => void applyPatches()} disabled={busy}>
                        Apply {agentReply.patches.length} patch{agentReply.patches.length === 1 ? "" : "es"}
                      </Button>
                    </div>
                  ) : null}
                </div>
              )}
            </div>
            <form
              className="shrink-0 border-t p-2"
              onSubmit={(event) => {
                event.preventDefault();
                void runAgent();
              }}
            >
              <Textarea
                value={prompt}
                onChange={(event) => setPrompt(event.target.value)}
                placeholder={agentMode === "plan" ? "Plan a refactor of hello.py…" : "Implement the approved plan…"}
                className="mb-2 min-h-20 text-sm"
              />
              <Button type="submit" className="w-full" disabled={busy}>
                {busy ? <LoaderCircle className="size-3.5 animate-spin" /> : <WandSparkles className="size-3.5" />}
                {agentMode === "plan" ? "Ask for a plan" : "Build"}
              </Button>
            </form>
          </aside>
        </div>
      )}
    </div>
  );
}
