import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import {
  MIC_PERMISSION_DENIED,
  MIN_CAPTURE_BYTES,
  NO_AUDIO_CAPTURED,
  pickRecorderMime,
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
  const startingRef = useRef(false);
  const pendingStopRef = useRef(false);
  const uploadAbortRef = useRef<AbortController | null>(null);
  const startedAtRef = useRef(0);
  const phaseRef = useRef<JuniorMicPhase>("idle");
  const activeModeRef = useRef<JuniorMicMode | null>(null);
  const onPhaseChangeRef = useRef(onPhaseChange);
  const onStsSubmitRef = useRef(onStsSubmit);
  const onSttDraftRef = useRef(onSttDraft);
  const registerAbortRef = useRef(registerAbort);

  onPhaseChangeRef.current = onPhaseChange;
  onStsSubmitRef.current = onStsSubmit;
  onSttDraftRef.current = onSttDraft;
  registerAbortRef.current = registerAbort;
  phaseRef.current = phase;
  activeModeRef.current = activeMode;

  const emitPhase = useCallback((next: JuniorMicPhase, mode: JuniorMicMode | null) => {
    phaseRef.current = next;
    activeModeRef.current = mode;
    setPhase(next);
    setActiveMode(mode);
    onPhaseChangeRef.current?.(next, mode);
  }, []);

  const cancelWithoutSend = useCallback(() => {
    console.log("junior-mic", { action: "cancel", mode: activeModeRef.current });
    uploadAbortRef.current?.abort();
    uploadAbortRef.current = null;
    sessionRef.current?.abort();
    sessionRef.current = null;
    startingRef.current = false;
    pendingStopRef.current = false;
    emitPhase("idle", null);
  }, [emitPhase]);

  const upload = useCallback(
    async (blob: Blob, mode: JuniorMicMode) => {
      const mime = blob.type || pickRecorderMime() || "unknown";
      console.log("junior-mic", { action: "upload", mode, mime, bytes: blob.size });
      if (blob.size < MIN_CAPTURE_BYTES) {
        toast.error(`${NO_AUDIO_CAPTURED} (${formatSttBlobHint(blob)})`);
        emitPhase("idle", null);
        return;
      }
      emitPhase("transcribing", mode);
      const controller = new AbortController();
      uploadAbortRef.current = controller;
      try {
        const result = await api.transcribeStt(blob, {
          signal: controller.signal,
          timeoutMs: STT_CLIP_TIMEOUT_MS,
        });
        const piece = (result.text || "").trim();
        console.log("junior-mic", { action: "stt-ok", mode, chars: piece.length });
        if (!piece) return;
        if (mode === "sts") onStsSubmitRef.current(piece);
        else onSttDraftRef.current(piece);
      } catch (error) {
        if (error instanceof ApiError) {
          console.log("junior-mic", { action: "stt-fail", mode, status: error.status, message: error.message });
          const message = error.message || sttFailToast(error.status);
          toast.error(message);
        } else if (!(error instanceof DOMException && error.name === "AbortError")) {
          console.log("junior-mic", {
            action: "stt-fail",
            mode,
            message: error instanceof Error ? error.message : "STT failed",
          });
          toast.error(sttFailToast(0, error instanceof Error ? error.message : "STT failed"));
        }
      } finally {
        uploadAbortRef.current = null;
        emitPhase("idle", null);
      }
    },
    [emitPhase],
  );

  const stopAndProcess = useCallback(async () => {
    pendingStopRef.current = false;
    const mode = activeModeRef.current;
    const session = sessionRef.current;
    console.log("junior-mic", { action: "stop", mode, hasSession: Boolean(session) });
    if (!mode) {
      emitPhase("idle", null);
      return;
    }
    if (!session) {
      if (phaseRef.current === "listening" || startingRef.current) pendingStopRef.current = true;
      else emitPhase("idle", null);
      return;
    }
    sessionRef.current = null;
    startingRef.current = false;
    try {
      const blob = await session.stop();
      await upload(blob, mode);
    } catch (error) {
      console.log("junior-mic", {
        action: "stop-fail",
        mode,
        message: error instanceof Error ? error.message : "STT failed",
      });
      toast.error(sttFailToast(0, error instanceof Error ? error.message : "STT failed"));
      emitPhase("idle", null);
    }
  }, [emitPhase, upload]);

  const abort = useCallback(() => {
    cancelWithoutSend();
  }, [cancelWithoutSend]);

  useEffect(() => {
    registerAbortRef.current?.(abort);
    return () => registerAbortRef.current?.(null);
  }, [abort]);

  // Unmount only — never tie cleanup to abort identity (parent re-renders were aborting mid-record).
  useEffect(() => {
    return () => {
      uploadAbortRef.current?.abort();
      sessionRef.current?.abort();
      sessionRef.current = null;
      startingRef.current = false;
    };
  }, []);

  const start = useCallback(
    async (mode: JuniorMicMode) => {
      if (phaseRef.current === "transcribing") {
        console.log("junior-mic", { action: "start-skip", mode, reason: "transcribing" });
        return;
      }
      if (activeModeRef.current && activeModeRef.current !== mode) {
        cancelWithoutSend();
      }
      if (sessionRef.current || startingRef.current) {
        console.log("junior-mic", { action: "start-skip", mode, reason: "already-active" });
        return;
      }

      startingRef.current = true;
      startedAtRef.current = Date.now();
      activeModeRef.current = mode;
      emitPhase("listening", mode);
      const mimeHint = pickRecorderMime() || "audio/wav-fallback";
      console.log("junior-mic", { action: "start", mode, mime: mimeHint });

      try {
        const session = await startMicClip({
          onPermissionRevoked: () => {
            console.log("junior-mic", { action: "permission-revoked", mode });
            sessionRef.current = null;
            startingRef.current = false;
            emitPhase("idle", null);
            toast.error(MIC_DENIED_TOAST);
          },
        });
        if (phaseRef.current !== "listening" || activeModeRef.current !== mode) {
          console.log("junior-mic", { action: "start-abort", mode, reason: "phase-changed" });
          session.abort();
          startingRef.current = false;
          return;
        }
        sessionRef.current = session;
        startingRef.current = false;
        console.log("junior-mic", { action: "recording", mode, mime: mimeHint });
        if (pendingStopRef.current) {
          pendingStopRef.current = false;
          window.setTimeout(() => {
            if (sessionRef.current === session) void stopAndProcess();
          }, MIC_TOGGLE_DEBOUNCE_MS);
        }
      } catch (error) {
        sessionRef.current = null;
        startingRef.current = false;
        emitPhase("idle", null);
        console.log("junior-mic", {
          action: "start-fail",
          mode,
          name: error instanceof DOMException ? error.name : undefined,
          message: error instanceof Error ? error.message : String(error),
        });
        if (error instanceof DOMException && error.message === MIC_PERMISSION_DENIED) {
          toast.error(MIC_PERMISSION_DENIED);
        } else if (error instanceof DOMException && error.name === "SecurityError") {
          toast.error("Microphone requires HTTPS (secure context).");
        } else if (error instanceof DOMException && error.name === "NotFoundError") {
          toast.error("No microphone found.");
        } else {
          toast.error(micDeniedMessage(error) || MIC_DENIED_TOAST);
        }
      }
    },
    [cancelWithoutSend, emitPhase, stopAndProcess],
  );

  const toggleMic = useCallback(
    (mode: JuniorMicMode) => {
      console.log("junior-mic", { action: "tap", mode, phase: phaseRef.current, enabled });
      if (phaseRef.current === "transcribing" || !enabled) {
        console.log("junior-mic", { action: "tap-ignored", mode, reason: !enabled ? "disabled" : "transcribing" });
        return;
      }
      const recordingThis =
        activeModeRef.current === mode &&
        (phaseRef.current === "listening" || startingRef.current || Boolean(sessionRef.current));
      if (recordingThis) {
        if (Date.now() - startedAtRef.current < MIC_TOGGLE_DEBOUNCE_MS) {
          console.log("junior-mic", { action: "tap-ignored", mode, reason: "debounce" });
          return;
        }
        void stopAndProcess();
        return;
      }
      if (activeModeRef.current && activeModeRef.current !== mode) {
        cancelWithoutSend();
      }
      void start(mode);
    },
    [cancelWithoutSend, enabled, start, stopAndProcess],
  );

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (phaseRef.current === "idle") return;
      event.preventDefault();
      if (phaseRef.current === "listening") {
        if (Date.now() - startedAtRef.current < MIC_TOGGLE_DEBOUNCE_MS) return;
        void stopAndProcess();
        return;
      }
      abort();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [abort, stopAndProcess]);

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
          event.stopPropagation();
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
