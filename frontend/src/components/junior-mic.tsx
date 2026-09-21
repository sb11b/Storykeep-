import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import {
  MIC_PERMISSION_DENIED,
  MIN_CAPTURE_BYTES,
  NO_AUDIO_CAPTURED,
  startMicClip,
  sttFailToast,
  type MicClipSession,
} from "@/lib/junior-stt";
import { STT_CLIP_TIMEOUT_MS } from "@/lib/stt-clip-client";
import { formatSttBlobHint } from "@/lib/stt-upload";
import { MIC_DENIED_TOAST, MIC_LIVE, MIC_TRANSCRIBING, micDeniedMessage } from "@/lib/stt-ui";
import { cn } from "@/lib/utils";

/** Ignore a second tap right after start so one gesture is not start+stop. */
export const MIC_TOGGLE_DEBOUNCE_MS = 300;

export type JuniorMicMode = "sts" | "stt";
export type JuniorMicPhase = "idle" | "listening" | "transcribing";

export function JuniorMicControls({
  enabled,
  locked,
  onStsSubmit,
  onSttDraft,
  onPhaseChange,
  registerAbort,
}: {
  enabled: boolean;
  locked: boolean;
  /** STS: put transcript in composer and auto-send. */
  onStsSubmit: (transcript: string) => void;
  /** STT: put transcript in composer only — never auto-send. */
  onSttDraft: (transcript: string) => void;
  onPhaseChange?: (phase: JuniorMicPhase, mode: JuniorMicMode | null) => void;
  registerAbort?: (abort: (() => void) | null) => void;
}) {
  const [phase, setPhase] = useState<JuniorMicPhase>("idle");
  const [activeMode, setActiveMode] = useState<JuniorMicMode | null>(null);
  const sessionRef = useRef<MicClipSession | null>(null);
  const listeningRef = useRef(false);
  const pendingStopRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  const startedAtRef = useRef(0);
  const activeModeRef = useRef<JuniorMicMode | null>(null);
  activeModeRef.current = activeMode;
  listeningRef.current = phase === "listening";

  const emitPhase = useCallback(
    (next: JuniorMicPhase, mode: JuniorMicMode | null) => {
      setPhase(next);
      setActiveMode(mode);
      onPhaseChange?.(next, mode);
    },
    [onPhaseChange],
  );

  const cancelWithoutSend = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    sessionRef.current?.abort();
    sessionRef.current = null;
    listeningRef.current = false;
    pendingStopRef.current = false;
    emitPhase("idle", null);
  }, [emitPhase]);

  const upload = useCallback(
    async (blob: Blob, mode: JuniorMicMode) => {
      if (blob.size < MIN_CAPTURE_BYTES) {
        toast.error(`${NO_AUDIO_CAPTURED} (${formatSttBlobHint(blob)})`);
        emitPhase("idle", null);
        return;
      }
      emitPhase("transcribing", mode);
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const result = await api.transcribeStt(blob, {
          signal: controller.signal,
          timeoutMs: STT_CLIP_TIMEOUT_MS,
        });
        const piece = (result.text || "").trim();
        if (!piece) return;
        if (mode === "sts") onStsSubmit(piece);
        else onSttDraft(piece);
      } catch (error) {
        if (error instanceof ApiError) {
          const message = error.message || sttFailToast(error.status);
          toast.error(message);
        } else if (!(error instanceof DOMException && error.name === "AbortError")) {
          toast.error(sttFailToast(0, error instanceof Error ? error.message : "STT failed"));
        }
      } finally {
        abortRef.current = null;
        emitPhase("idle", null);
      }
    },
    [emitPhase, onStsSubmit, onSttDraft],
  );

  const stopAndProcess = useCallback(async () => {
    pendingStopRef.current = false;
    const mode = activeModeRef.current;
    const session = sessionRef.current;
    if (!mode) {
      emitPhase("idle", null);
      return;
    }
    if (!session) {
      if (listeningRef.current) pendingStopRef.current = true;
      else emitPhase("idle", null);
      return;
    }
    sessionRef.current = null;
    listeningRef.current = false;
    try {
      const blob = await session.stop();
      await upload(blob, mode);
    } catch (error) {
      toast.error(sttFailToast(0, error instanceof Error ? error.message : "STT failed"));
      emitPhase("idle", null);
    }
  }, [emitPhase, upload]);

  const abort = useCallback(() => {
    cancelWithoutSend();
  }, [cancelWithoutSend]);

  useEffect(() => {
    registerAbort?.(abort);
    return () => registerAbort?.(null);
  }, [abort, registerAbort]);

  const start = useCallback(
    async (mode: JuniorMicMode) => {
      if (phase === "transcribing") return;
      if (activeModeRef.current && activeModeRef.current !== mode) {
        cancelWithoutSend();
      }
      if (listeningRef.current || sessionRef.current) return;
      listeningRef.current = true;
      startedAtRef.current = Date.now();
      emitPhase("listening", mode);
      try {
        const session = await startMicClip({
          onPermissionRevoked: () => {
            sessionRef.current = null;
            listeningRef.current = false;
            emitPhase("idle", null);
            toast.error(MIC_DENIED_TOAST);
          },
        });
        if (!listeningRef.current && !pendingStopRef.current) {
          session.abort();
          return;
        }
        sessionRef.current = session;
        if (pendingStopRef.current) {
          pendingStopRef.current = false;
          window.setTimeout(() => {
            if (sessionRef.current === session) void stopAndProcess();
          }, MIC_TOGGLE_DEBOUNCE_MS);
        }
      } catch (error) {
        sessionRef.current = null;
        listeningRef.current = false;
        emitPhase("idle", null);
        if (error instanceof DOMException && error.message === MIC_PERMISSION_DENIED) {
          toast.error(MIC_PERMISSION_DENIED);
        } else {
          toast.error(micDeniedMessage(error) || MIC_DENIED_TOAST);
        }
      }
    },
    [cancelWithoutSend, emitPhase, phase, stopAndProcess],
  );

  const toggleMic = useCallback(
    (mode: JuniorMicMode) => {
      if (phase === "transcribing" || !enabled) return;
      const isActive = activeModeRef.current === mode && (listeningRef.current || sessionRef.current);
      if (isActive) {
        if (Date.now() - startedAtRef.current < MIC_TOGGLE_DEBOUNCE_MS) return;
        void stopAndProcess();
        return;
      }
      if (activeModeRef.current && activeModeRef.current !== mode) {
        cancelWithoutSend();
      }
      void start(mode);
    },
    [cancelWithoutSend, enabled, phase, start, stopAndProcess],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (phase === "idle") return;
      event.preventDefault();
      if (phase === "listening") {
        if (Date.now() - startedAtRef.current < MIC_TOGGLE_DEBOUNCE_MS) return;
        void stopAndProcess();
        return;
      }
      abort();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [abort, phase, stopAndProcess]);

  useEffect(() => () => abort(), [abort]);

  if (locked || !enabled) return null;

  function renderButton(mode: JuniorMicMode, label: string, idleTitle: string, liveTitle: string) {
    const mine = activeMode === mode;
    const listening = mine && phase === "listening";
    const transcribing = mine && phase === "transcribing";
    const disabled = transcribing || (phase !== "idle" && !mine);

    return (
      <Button
        key={mode}
        type="button"
        size="sm"
        variant={listening ? "destructive" : "outline"}
        className={cn("relative z-10 h-9 shrink-0 px-2.5 text-xs font-medium", transcribing && "min-w-[3.25rem]")}
        disabled={disabled}
        aria-label={
          listening ? `${label} — ${MIC_LIVE}` : transcribing ? `${label} — ${MIC_TRANSCRIBING}` : label
        }
        aria-pressed={listening}
        data-mic-mode={mode}
        data-mic-state={listening ? "live" : transcribing ? "uploading" : "idle"}
        title={
          listening ? liveTitle : transcribing ? MIC_TRANSCRIBING : idleTitle
        }
        onClick={(event) => {
          event.preventDefault();
          toggleMic(mode);
        }}
      >
        {transcribing ? <LoaderCircle className="mr-1 size-3.5 animate-spin" /> : null}
        {label}
        {listening ? "…" : ""}
      </Button>
    );
  }

  return (
    <>
      {renderButton(
        "sts",
        "STS",
        "Speech-to-speech — tap to talk, tap again to send",
        `${MIC_LIVE} — tap again to send`,
      )}
      {renderButton(
        "stt",
        "STT",
        "Speech-to-text — tap to talk, tap again to fill composer",
        `${MIC_LIVE} — tap again to transcribe`,
      )}
    </>
  );
}
