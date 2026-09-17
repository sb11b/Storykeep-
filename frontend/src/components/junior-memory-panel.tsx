"use client";

import { useCallback, useEffect, useState, type Ref } from "react";
import { ChevronLeft, LoaderCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { api } from "@/lib/api";
import { toastActionError } from "@/lib/toast-message";

const SAVE_CHARS = 100_000;

export function JuniorMemoryPanel({
  railRef,
  onHide,
}: {
  railRef?: Ref<HTMLElement | null>;
  onHide?: () => void;
}) {
  const [markdown, setMarkdown] = useState("");
  const [updatedAt, setUpdatedAt] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await api.juniorMemory();
      setMarkdown(payload.markdown || "");
      setUpdatedAt(payload.updated_at);
    } catch (caught) {
      setError("Could not load memory.");
      toastActionError(caught, "load Junior memory", "Could not load Junior memory.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function save() {
    if (markdown.length > SAVE_CHARS) {
      toast.error("Memory note is too long.");
      return;
    }
    setSaving(true);
    try {
      const payload = await api.putJuniorMemory(markdown);
      setMarkdown(payload.markdown || "");
      setUpdatedAt(payload.updated_at);
      toast.success("Memory saved");
    } catch (caught) {
      toastActionError(caught, "save Junior memory", "Could not save Junior memory.");
    } finally {
      setSaving(false);
    }
  }

  const when = updatedAt
    ? new Date(updatedAt).toLocaleString(undefined, {
        month: "short",
        day: "numeric",
        hour: "numeric",
        minute: "2-digit",
      })
    : null;

  return (
    <aside ref={railRef} className="flex w-64 shrink-0 flex-col overflow-hidden border-r bg-muted/15">
      <div className="flex shrink-0 items-center justify-between gap-1 border-b p-2">
        <p className="text-[11px] uppercase tracking-wide text-muted-foreground">Memory</p>
        <div className="flex items-center gap-1">
          {onHide ? (
            <Button
              type="button"
              size="icon-xs"
              variant="ghost"
              aria-label="Hide Memory"
              aria-expanded={true}
              title="Hide Memory"
              onClick={onHide}
            >
              <ChevronLeft className="size-3.5" />
            </Button>
          ) : null}
          <Button size="xs" variant="outline" disabled={saving || loading} onClick={() => void save()}>
            {saving ? <LoaderCircle className="size-3 animate-spin" /> : null}
            Save
          </Button>
        </div>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-1.5 p-2">
        {loading ? (
          <p className="flex items-center gap-1 px-1 py-2 text-[11px] text-muted-foreground">
            <LoaderCircle className="size-3 animate-spin" />
            Loading…
          </p>
        ) : error ? (
          <div className="space-y-2 px-1 py-2">
            <p className="text-[11px] text-muted-foreground">{error}</p>
            <Button size="xs" variant="outline" onClick={() => void load()}>
              Retry
            </Button>
          </div>
        ) : (
          <>
            <Textarea
              value={markdown}
              onChange={(event) => setMarkdown(event.target.value)}
              className="min-h-0 flex-1 resize-none text-[12px] leading-snug"
              dictate={false}
              aria-label="Junior memory note"
              placeholder="Standing context for Junior. Saved here, not dumped into replies."
            />
            <p className="text-[10px] text-muted-foreground">
              {markdown.length.toLocaleString()} / {SAVE_CHARS.toLocaleString()}
              {when ? ` · saved ${when}` : " · not saved yet"}
            </p>
          </>
        )}
      </div>
    </aside>
  );
}
