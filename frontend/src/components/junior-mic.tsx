import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import {
  MIC_PERMISSION_DENIED,
  MIN_CAPTURE_BYTES,
  nextMicRestartDelay,
  NO_AUDIO_CAPTURED,
  pickRecorderMime,
  shouldRestartMic,
  startMicClip,
  sttFailToast,
  type MicClipSession,
} from "@/lib/junior-stt";
import { STT_CLIP_TIMEOUT_MS } from "@/lib/stt-clip-client";
import { formatSttBlobHint, isSttEmptyError } from "@/lib/stt-upload";
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
  onSttEmptyHint,
  onPhaseChange,
  onStsModeChange,
  registerAbort,
  registerStsRearm,
}: {
  enabled: boolean;
  locked: boolean;
  /** STS: auto-send transcript as user message. */
  onStsSubmit: (transcript: string) => void;
  /** STT: composer only — never auto-send. */
  onSttDraft: (transcript: string) => void;
  /** Blank STT/STS take — show in composer chrome, never send or overwrite draft. */
  onSttEmptyHint?: () => void;
  onPhaseChange?: (phase: JuniorMicPhase, mode: JuniorMicMode | null) => void;
  onStsModeChange?: (active: boolean) => void;
  registerAbort?: (abort: (() => void) | null) => void;
  /** Parent calls this after Castor ends to start the next STS take. */
  registerStsRearm?: (rearm: (() => void) | null) => void;
}) {
  const [phase, setPhase] = useState<JuniorMicPhase>("idle");
  const [activeMode, setActiveMode] = useState<JuniorMicMode | null>(null);
  const [stsModeOn, setStsModeOn] = useState(false);
  const sessionRef = useRef<MicClipSession | null>(null);
  const startingRef = useRef(false);
  const pendingStopRef = useRef(false);
  const uploadAbortRef = useRef<AbortController | null>(null);
  const startedAtRef = useRef(0);
  const phaseRef = useRef<JuniorMicPhase>("idle");
  const activeModeRef = useRef<JuniorMicMode | null>(null);
  const stsModeOnRef = useRef(false);
  const processingRef = useRef(false);
  const rearmStsRecordingRef = useRef<(() => void) | null>(null);
  const restartTimerRef = useRef<number | null>(null);
  const restartDelayRef = useRef(0);
  const lastRestartAtRef = useRef(0);
  const onPhaseChangeRef = useRef(onPhaseChange);
  const onStsModeChangeRef = useRef(onStsModeChange);
  const onStsSubmitRef = useRef(onStsSubmit);
  const onSttDraftRef = useRef(onSttDraft);
  const onSttEmptyHintRef = useRef(onSttEmptyHint);
  const registerAbortRef = useRef(registerAbort);
  const registerStsRearmRef = useRef(registerStsRearm);

  onPhaseChangeRef.current = onPhaseChange;
  onStsModeChangeRef.current = onStsModeChange;
  onStsSubmitRef.current = onStsSubmit;
  onSttDraftRef.current = onSttDraft;
  onSttEmptyHintRef.current = onSttEmptyHint;
  registerAbortRef.current = registerAbort;
  registerStsRearmRef.current = registerStsRearm;
  phaseRef.current = phase;
  activeModeRef.current = activeMode;
  stsModeOnRef.current = stsModeOn;

  const setStsMode = useCallback((next: boolean) => {
    stsModeOnRef.current = next;
    setStsModeOn(next);
    onStsModeChangeRef.current?.(next);
    console.log("junior-mic", { action: "sts-mode", on: next });
  }, []);

  const emitPhase = useCallback((next: JuniorMicPhase, mode: JuniorMicMode | null) => {
    phaseRef.current = next;
    activeModeRef.current = mode;
    setPhase(next);
    setActiveMode(mode);
    onPhaseChangeRef.current?.(next, mode);
  }, []);

  const abortSessionOnly = useCallback(() => {
    if (restartTimerRef.current != null) {
      window.clearTimeout(restartTimerRef.current);
      restartTimerRef.current = null;
    }
    uploadAbortRef.current?.abort();
    uploadAbortRef.current = null;
    sessionRef.current?.abort();
    sessionRef.current = null;
    startingRef.current = false;
    pendingStopRef.current = false;
    processingRef.current = false;
  }, []);

  const cancelAll = useCallback(() => {
    console.log("junior-mic", { action: "cancel", mode: activeModeRef.current, stsMode: stsModeOnRef.current });
    abortSessionOnly();
    setStsMode(false);
    emitPhase("idle", null);
  }, [abortSessionOnly, emitPhase, setStsMode]);

  const showMicError = useCallback((error: unknown, mode: JuniorMicMode) => {
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
  }, []);

  const transcribeSttInBackground = useCallback(async (blob: Blob) => {
    if (blob.size < MIN_CAPTURE_BYTES) return;
    const controller = new AbortController();
    uploadAbortRef.current = controller;
    try {
      const result = await api.transcribeStt(blob, {
        signal: controller.signal,
        timeoutMs: STT_CLIP_TIMEOUT_MS,
      });
      const piece = (result.text || "").trim();
      if (piece) onSttDraftRef.current(piece);
    } catch (error) {
      if (isSttEmptyError(error)) onSttEmptyHintRef.current?.();
      else if (error instanceof ApiError) toast.error(error.message || sttFailToast(error.status));
      else if (!(error instanceof DOMException && error.name === "AbortError")) {
        toast.error(sttFailToast(0, error instanceof Error ? error.message : "STT failed"));
      }
    } finally {
      if (uploadAbortRef.current === controller) uploadAbortRef.current = null;
    }
  }, []);

  const scheduleMicRestart = useCallback((mode: JuniorMicMode, fromError: boolean, start: () => void) => {
    const delay = nextMicRestartDelay({
      fromError,
      prevDelayMs: restartDelayRef.current,
      elapsedSinceRestartMs: Date.now() - lastRestartAtRef.current,
    });
    restartDelayRef.current = delay || 0;
    lastRestartAtRef.current = Date.now();
    if (restartTimerRef.current != null) window.clearTimeout(restartTimerRef.current);
    restartTimerRef.current = window.setTimeout(() => {
      restartTimerRef.current = null;
      start();
    }, delay);
    console.log("junior-mic", { action: "engine-restart", mode, delay });
  }, []);

  const uploadSttDraft = useCallback(
    async (blob: Blob) => {
      const mime = blob.type || pickRecorderMime() || "unknown";
      console.log("junior-mic", { action: "upload", mode: "stt", mime, bytes: blob.size, trigger: "button" });
      if (blob.size < MIN_CAPTURE_BYTES) {
        toast.error(`${NO_AUDIO_CAPTURED} (${formatSttBlobHint(blob)})`);
        emitPhase("idle", null);
        return;
      }
      emitPhase("transcribing", "stt");
      const controller = new AbortController();
      uploadAbortRef.current = controller;
      try {
        const result = await api.transcribeStt(blob, {
          signal: controller.signal,
          timeoutMs: STT_CLIP_TIMEOUT_MS,
        });
        const piece = (result.text || "").trim();
        console.log("junior-mic", { action: "stt-ok", mode: "stt", chars: piece.length });
        if (piece) onSttDraftRef.current(piece);
      } catch (error) {
        if (isSttEmptyError(error)) {
          console.log("junior-mic", { action: "stt-empty", mode: "stt" });
          onSttEmptyHintRef.current?.();
        } else if (error instanceof ApiError) {
          console.log("junior-mic", { action: "stt-fail", mode: "stt", status: error.status, message: error.message });
          toast.error(error.message || sttFailToast(error.status));
        } else if (!(error instanceof DOMException && error.name === "AbortError")) {
          toast.error(sttFailToast(0, error instanceof Error ? error.message : "STT failed"));
        }
      } finally {
        uploadAbortRef.current = null;
        emitPhase("idle", null);
      }
    },
    [emitPhase],
  );

  const uploadStsTake = useCallback(
    async (blob: Blob, trigger: "silence" | "button") => {
      const mime = blob.type || pickRecorderMime() || "unknown";
      console.log("junior-mic", { action: "upload", mode: "sts", mime, bytes: blob.size, trigger });
      if (blob.size < MIN_CAPTURE_BYTES) {
        toast.error(`${NO_AUDIO_CAPTURED} (${formatSttBlobHint(blob)})`);
        if (stsModeOnRef.current) {
          emitPhase("idle", null);
          void rearmStsRecordingRef.current?.();
        } else {
          emitPhase("idle", null);
        }
        return;
      }
      emitPhase("transcribing", "sts");
      const controller = new AbortController();
      uploadAbortRef.current = controller;
      try {
        const result = await api.transcribeStt(blob, {
          signal: controller.signal,
          timeoutMs: STT_CLIP_TIMEOUT_MS,
        });
        const piece = (result.text || "").trim();
        console.log("junior-mic", { action: "stt-ok", mode: "sts", chars: piece.length, trigger });
        if (!piece) {
          console.log("junior-mic", { action: "stt-empty", mode: "sts", trigger });
          onSttEmptyHintRef.current?.();
          if (stsModeOnRef.current) void rearmStsRecordingRef.current?.();
          return;
        }
        onStsSubmitRef.current(piece);
        if (stsModeOnRef.current) emitPhase("idle", null);
      } catch (error) {
        if (isSttEmptyError(error)) {
          console.log("junior-mic", { action: "stt-empty", mode: "sts", trigger });
          onSttEmptyHintRef.current?.();
        } else if (error instanceof ApiError) {
          console.log("junior-mic", { action: "stt-fail", mode: "sts", status: error.status, message: error.message });
          toast.error(error.message || sttFailToast(error.status));
        } else if (!(error instanceof DOMException && error.name === "AbortError")) {
          toast.error(sttFailToast(0, error instanceof Error ? error.message : "STT failed"));
        }
        if (stsModeOnRef.current) void rearmStsRecordingRef.current?.();
      } finally {
        uploadAbortRef.current = null;
        if (!stsModeOnRef.current) emitPhase("idle", null);
        else if (phaseRef.current === "transcribing") emitPhase("idle", null);
      }
    },
    [emitPhase],
  );

  const processStsTake = useCallback(
    async (trigger: "silence" | "button") => {
      if (processingRef.current) return;
      const session = sessionRef.current;
      if (!session || !stsModeOnRef.current) return;
      processingRef.current = true;
      sessionRef.current = null;
      startingRef.current = false;
      console.log("junior-mic", { action: "stop", mode: "sts", trigger, hasSession: true });
      try {
        const blob = await session.stop();
        await uploadStsTake(blob, trigger);
      } catch (error) {
        console.log("junior-mic", {
          action: "stop-fail",
          mode: "sts",
          trigger,
          message: error instanceof Error ? error.message : "STT failed",
        });
        toast.error(sttFailToast(0, error instanceof Error ? error.message : "STT failed"));
        if (stsModeOnRef.current) void rearmStsRecordingRef.current?.();
        else emitPhase("idle", null);
      } finally {
        processingRef.current = false;
      }
    },
    [emitPhase, uploadStsTake],
  );

  const stopSttAndUpload = useCallback(async () => {
    pendingStopRef.current = false;
    const session = sessionRef.current;
    console.log("junior-mic", { action: "stop", mode: "stt", trigger: "button", hasSession: Boolean(session) });
    if (!session) {
      if (restartTimerRef.current != null) {
        window.clearTimeout(restartTimerRef.current);
        restartTimerRef.current = null;
        emitPhase("idle", null);
        return;
      }
      if (phaseRef.current === "listening" || startingRef.current) pendingStopRef.current = true;
      else emitPhase("idle", null);
      return;
    }
    sessionRef.current = null;
    startingRef.current = false;
    try {
      const blob = await session.stop();
      await uploadSttDraft(blob);
    } catch (error) {
      toast.error(sttFailToast(0, error instanceof Error ? error.message : "STT failed"));
      emitPhase("idle", null);
    }
  }, [emitPhase, uploadSttDraft]);

  const exitStsMode = useCallback(
    (reason: "button" | "escape" | "stt-cancel") => {
      console.log("junior-mic", { action: "sts-exit", reason });
      abortSessionOnly();
      setStsMode(false);
      emitPhase("idle", null);
    },
    [abortSessionOnly, emitPhase, setStsMode],
  );

  const startStsRecording = useCallback(async () => {
    if (!stsModeOnRef.current || phaseRef.current === "transcribing") return;
    if (sessionRef.current || startingRef.current || processingRef.current) return;

    startingRef.current = true;
    startedAtRef.current = Date.now();
    emitPhase("listening", "sts");
    const mimeHint = pickRecorderMime() || "audio/wav-fallback";
    console.log("junior-mic", { action: "start", mode: "sts", mime: mimeHint });

    try {
      const session = await startMicClip({
        onPermissionRevoked: () => {
          console.log("junior-mic", { action: "permission-revoked", mode: "sts" });
          sessionRef.current = null;
          startingRef.current = false;
          setStsMode(false);
          emitPhase("idle", null);
          toast.error(MIC_DENIED_TOAST);
        },
        onSilenceEnd: () => {
          if (!stsModeOnRef.current || sessionRef.current !== session) return;
          console.log("junior-mic", { action: "silence-end", mode: "sts" });
          void processStsTake("silence");
        },
        onEngineEnd: () => {
          if (!stsModeOnRef.current || sessionRef.current !== session) return;
          console.log("junior-mic", { action: "engine-end", mode: "sts" });
          if (shouldRestartMic(true, "engine")) void processStsTake("silence");
        },
      });
      if (!stsModeOnRef.current) {
        session.abort();
        startingRef.current = false;
        emitPhase("idle", null);
        return;
      }
      sessionRef.current = session;
      startingRef.current = false;
      restartDelayRef.current = 0;
      console.log("junior-mic", { action: "recording", mode: "sts", mime: mimeHint });
    } catch (error) {
      sessionRef.current = null;
      startingRef.current = false;
      setStsMode(false);
      emitPhase("idle", null);
      showMicError(error, "sts");
    }
  }, [emitPhase, processStsTake, setStsMode, showMicError]);

  rearmStsRecordingRef.current = () => {
    if (!stsModeOnRef.current || !enabled) return;
    if (phaseRef.current !== "idle" || sessionRef.current || startingRef.current || processingRef.current) {
      console.log("junior-mic", { action: "rearm-skip", phase: phaseRef.current });
      return;
    }
    console.log("junior-mic", { action: "rearm", mode: "sts" });
    void startStsRecording();
  };

  const startSttRecording = useCallback(async () => {
    if (phaseRef.current === "transcribing") return;
    if (stsModeOnRef.current) exitStsMode("stt-cancel");
    if (sessionRef.current || startingRef.current) return;

    startingRef.current = true;
    startedAtRef.current = Date.now();
    emitPhase("listening", "stt");
    const mimeHint = pickRecorderMime() || "audio/wav-fallback";
    console.log("junior-mic", { action: "start", mode: "stt", mime: mimeHint });

    try {
      const session = await startMicClip({
        onPermissionRevoked: () => {
          sessionRef.current = null;
          startingRef.current = false;
          emitPhase("idle", null);
          toast.error(MIC_DENIED_TOAST);
        },
        onEngineEnd: () => {
          if (sessionRef.current !== session || activeModeRef.current !== "stt") return;
          if (!shouldRestartMic(phaseRef.current === "listening", "engine")) {
            emitPhase("idle", null);
            return;
          }
          console.log("junior-mic", { action: "engine-end", mode: "stt" });
          sessionRef.current = null;
          startingRef.current = false;
          void session
            .stop()
            .then((blob) => {
              if (blob.size >= MIN_CAPTURE_BYTES) void transcribeSttInBackground(blob);
            })
            .catch(() => {});
          scheduleMicRestart("stt", true, () => {
            if (phaseRef.current === "listening" && activeModeRef.current === "stt") {
              void startSttRecording();
            }
          });
        },
      });
      if (phaseRef.current !== "listening" || activeModeRef.current !== "stt") {
        session.abort();
        startingRef.current = false;
        return;
      }
      sessionRef.current = session;
      startingRef.current = false;
      restartDelayRef.current = 0;
      console.log("junior-mic", { action: "recording", mode: "stt", mime: mimeHint });
      if (pendingStopRef.current) {
        pendingStopRef.current = false;
        window.setTimeout(() => {
          if (sessionRef.current === session) void stopSttAndUpload();
        }, MIC_TOGGLE_DEBOUNCE_MS);
      }
    } catch (error) {
      sessionRef.current = null;
      startingRef.current = false;
      emitPhase("idle", null);
      showMicError(error, "stt");
    }
  }, [emitPhase, exitStsMode, scheduleMicRestart, showMicError, stopSttAndUpload, transcribeSttInBackground]);

  const toggleSts = useCallback(() => {
    console.log("junior-mic", { action: "tap", mode: "sts", phase: phaseRef.current, stsMode: stsModeOnRef.current, enabled });
    if (!enabled || phaseRef.current === "transcribing") return;

    if (stsModeOnRef.current) {
      if (Date.now() - startedAtRef.current < MIC_TOGGLE_DEBOUNCE_MS && phaseRef.current === "listening") {
        console.log("junior-mic", { action: "tap-ignored", mode: "sts", reason: "debounce" });
        return;
      }
      exitStsMode("button");
      return;
    }

    if (activeModeRef.current === "stt") abortSessionOnly();
    setStsMode(true);
    void startStsRecording();
  }, [abortSessionOnly, enabled, exitStsMode, setStsMode, startStsRecording]);

  const toggleStt = useCallback(() => {
    console.log("junior-mic", { action: "tap", mode: "stt", phase: phaseRef.current, enabled });
    if (phaseRef.current === "transcribing" || !enabled) return;

    const recordingStt =
      activeModeRef.current === "stt" &&
      (phaseRef.current === "listening" || startingRef.current || Boolean(sessionRef.current));
    if (recordingStt) {
      if (Date.now() - startedAtRef.current < MIC_TOGGLE_DEBOUNCE_MS) return;
      void stopSttAndUpload();
      return;
    }
    if (stsModeOnRef.current) exitStsMode("stt-cancel");
    void startSttRecording();
  }, [enabled, exitStsMode, startSttRecording, stopSttAndUpload]);

  const abort = useCallback(() => {
    cancelAll();
  }, [cancelAll]);

  useEffect(() => {
    registerAbortRef.current?.(abort);
    return () => registerAbortRef.current?.(null);
  }, [abort]);

  useEffect(() => {
    registerStsRearmRef.current?.(() => rearmStsRecordingRef.current?.());
    return () => registerStsRearmRef.current?.(null);
  }, []);

  useEffect(() => {
    return () => {
      uploadAbortRef.current?.abort();
      sessionRef.current?.abort();
      sessionRef.current = null;
    };
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (phaseRef.current === "idle" && !stsModeOnRef.current) return;
      event.preventDefault();
      if (stsModeOnRef.current) {
        exitStsMode("escape");
        return;
      }
      if (phaseRef.current === "listening" && activeModeRef.current === "stt") {
        if (Date.now() - startedAtRef.current < MIC_TOGGLE_DEBOUNCE_MS) return;
        void stopSttAndUpload();
        return;
      }
      if (phaseRef.current === "transcribing") abortSessionOnly();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [abortSessionOnly, exitStsMode, stopSttAndUpload]);

  if (locked || !enabled) return null;

  function renderStsButton() {
    const live = stsModeOn && phase === "listening";
    const transcribing = stsModeOn && phase === "transcribing";
    const latched = stsModeOn && !live && !transcribing;
    const disabled = transcribing || (phase !== "idle" && activeMode === "stt");

    return (
      <Button
        type="button"
        size="sm"
        variant={live || latched ? "destructive" : "outline"}
        className={cn(
          "relative z-10 h-9 shrink-0 px-2.5 text-xs font-medium",
          latched && "ring-2 ring-destructive/40",
          transcribing && "min-w-[3.25rem]",
        )}
        disabled={disabled}
        aria-label={live ? `STS — ${MIC_LIVE}` : transcribing ? `STS — ${MIC_TRANSCRIBING}` : "STS conversation mode"}
        aria-pressed={stsModeOn}
        data-mic-mode="sts"
        data-mic-state={live ? "live" : transcribing ? "uploading" : latched ? "latched" : "idle"}
        title={
          stsModeOn
            ? live
              ? `${MIC_LIVE} — silence sends; tap to end conversation`
              : latched
                ? "Conversation mode — waiting for reply; tap to end"
                : MIC_TRANSCRIBING
            : "Speech-to-speech — tap to start conversation mode"
        }
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          toggleSts();
        }}
      >
        {transcribing ? <LoaderCircle className="mr-1 size-3.5 animate-spin" /> : null}
        STS
        {live ? "…" : ""}
      </Button>
    );
  }

  function renderSttButton() {
    const live = activeMode === "stt" && phase === "listening";
    const transcribing = activeMode === "stt" && phase === "transcribing";
    const disabled = transcribing || (phase !== "idle" && activeMode !== "stt");

    return (
      <Button
        type="button"
        size="sm"
        variant={live ? "destructive" : "outline"}
        className={cn("relative z-10 h-9 shrink-0 px-2.5 text-xs font-medium", transcribing && "min-w-[3.25rem]")}
        disabled={disabled}
        aria-label={live ? `STT — ${MIC_LIVE}` : transcribing ? `STT — ${MIC_TRANSCRIBING}` : "STT"}
        aria-pressed={live}
        data-mic-mode="stt"
        data-mic-state={live ? "live" : transcribing ? "uploading" : "idle"}
        title={
          live
            ? `${MIC_LIVE} — tap again to transcribe`
            : transcribing
              ? MIC_TRANSCRIBING
              : "Speech-to-text — tap to talk, tap again to fill composer"
        }
        onClick={(event) => {
          event.preventDefault();
          event.stopPropagation();
          toggleStt();
        }}
      >
        {transcribing ? <LoaderCircle className="mr-1 size-3.5 animate-spin" /> : null}
        STT
        {live ? "…" : ""}
      </Button>
    );
  }

  return (
    <>
      {renderStsButton()}
      {renderSttButton()}
    </>
  );
}
