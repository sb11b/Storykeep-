import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, Mic } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { appendSpoken } from "@/lib/stt-buffer";
import {
  MAX_CLIP_MS,
  MIN_CLIP_BYTES,
  startMicClip,
  sttFailToast,
  type MicClipSession,
} from "@/lib/junior-stt";
import { MIC_DENIED_TOAST, MIC_IDLE, MIC_LIVE, micDeniedMessage } from "@/lib/stt-ui";

export function JuniorMicButton({
  enabled,
  locked,
  getDraft,
  onTranscript,
}: {
  enabled: boolean;
  locked: boolean;
  getDraft: () => string;
  onTranscript: (next: string) => void;
}) {
  const [phase, setPhase] = useState<"idle" | "recording" | "uploading">("idle");
  const sessionRef = useRef<MicClipSession | null>(null);
  const phaseRef = useRef(phase);
  phaseRef.current = phase;

  const upload = useCallback(
    async (blob: Blob) => {
      if (blob.size < MIN_CLIP_BYTES) {
        toast.error(sttFailToast(400, "empty blob"));
        setPhase("idle");
        return;
      }
      setPhase("uploading");
      try {
        const result = await api.transcribeStt(blob);
        const piece = (result.text || "").trim();
        if (!piece) {
          toast.error("STT failed (empty transcript)");
          setPhase("idle");
          return;
        }
        onTranscript(appendSpoken(getDraft(), piece));
      } catch (error) {
        if (error instanceof ApiError) {
          toast.error(sttFailToast(error.status, error.message));
        } else {
          toast.error(sttFailToast(0, error instanceof Error ? error.message : "STT failed"));
        }
      } finally {
        setPhase("idle");
      }
    },
    [getDraft, onTranscript],
  );

  const stopAndSend = useCallback(async () => {
    const session = sessionRef.current;
    sessionRef.current = null;
    if (!session) {
      setPhase("idle");
      return;
    }
    try {
      const blob = await session.stop();
      await upload(blob);
    } catch (error) {
      toast.error(sttFailToast(0, error instanceof Error ? error.message : "STT failed"));
      setPhase("idle");
    }
  }, [upload]);

  const abort = useCallback(() => {
    sessionRef.current?.abort();
    sessionRef.current = null;
    setPhase("idle");
  }, []);

  const start = useCallback(async () => {
    try {
      const session = await startMicClip({
        maxMs: MAX_CLIP_MS,
        onAutoStop: () => {
          void stopAndSend();
        },
      });
      sessionRef.current = session;
      setPhase("recording");
    } catch (error) {
      sessionRef.current = null;
      setPhase("idle");
      toast.error(micDeniedMessage(error) || MIC_DENIED_TOAST);
    }
  }, [stopAndSend]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (phaseRef.current !== "recording") return;
      event.preventDefault();
      abort();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [abort]);

  useEffect(() => () => abort(), [abort]);

  if (locked || !enabled) return null;

  const recording = phase === "recording";
  const uploading = phase === "uploading";
  return (
    <Button
      type="button"
      size="icon"
      variant={recording ? "destructive" : "outline"}
      className="relative z-10 size-9 shrink-0"
      disabled={uploading}
      aria-label={recording ? MIC_LIVE : uploading ? "Transcribing" : MIC_IDLE}
      data-mic-state={recording ? "live" : uploading ? "uploading" : "idle"}
      title={recording ? `${MIC_LIVE} — tap to stop` : `${MIC_IDLE} — tap to talk, tap again to insert`}
      onMouseDown={(event) => event.preventDefault()}
      onClick={() => {
        if (uploading) return;
        if (recording) {
          void stopAndSend();
          return;
        }
        void start();
      }}
    >
      {uploading ? <LoaderCircle className="size-4 animate-spin" /> : <Mic className="size-4" />}
    </Button>
  );
}
