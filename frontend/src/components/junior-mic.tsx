import { useCallback, useEffect, useRef, useState, type PointerEvent as ReactPointerEvent } from "react";
import { LoaderCircle, Mic } from "lucide-react";
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
import { MIC_DENIED_TOAST, MIC_IDLE, MIC_LIVE, MIC_TRANSCRIBING, micDeniedMessage } from "@/lib/stt-ui";

export type JuniorMicPhase = "idle" | "listening" | "transcribing";

export function JuniorMicButton({
  enabled,
  locked,
  onVoiceSubmit,
  onPhaseChange,
  registerAbort,
}: {
  enabled: boolean;
  locked: boolean;
  /** Fresh transcript from xAI — parent puts it in the composer and auto-sends. */
  onVoiceSubmit: (transcript: string) => void;
  onPhaseChange?: (phase: JuniorMicPhase) => void;
  registerAbort?: (abort: (() => void) | null) => void;
}) {
  const [phase, setPhase] = useState<JuniorMicPhase>("idle");
  const sessionRef = useRef<MicClipSession | null>(null);
  const listeningRef = useRef(false);
  const pointerDownRef = useRef(false);
  const pendingStopRef = useRef(false);
  const abortRef = useRef<AbortController | null>(null);
  listeningRef.current = phase === "listening";

  const setMicPhase = useCallback(
    (next: JuniorMicPhase) => {
      setPhase(next);
      onPhaseChange?.(next);
    },
    [onPhaseChange],
  );

  const upload = useCallback(
    async (blob: Blob) => {
      if (blob.size < MIN_CAPTURE_BYTES) {
        toast.error(NO_AUDIO_CAPTURED);
        setMicPhase("idle");
        return;
      }
      setMicPhase("transcribing");
      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const result = await api.transcribeStt(blob, {
          signal: controller.signal,
          timeoutMs: STT_CLIP_TIMEOUT_MS,
        });
        const piece = (result.text || "").trim();
        if (!piece) return;
        onVoiceSubmit(piece);
      } catch (error) {
        if (error instanceof ApiError) {
          toast.error(sttFailToast(error.status, error.message));
        } else if (!(error instanceof DOMException && error.name === "AbortError")) {
          toast.error(sttFailToast(0, error instanceof Error ? error.message : "STT failed"));
        }
      } finally {
        abortRef.current = null;
        setMicPhase("idle");
      }
    },
    [onVoiceSubmit, setMicPhase],
  );

  const stopAndSend = useCallback(async () => {
    pendingStopRef.current = false;
    const session = sessionRef.current;
    if (!session) {
      if (listeningRef.current) pendingStopRef.current = true;
      else setMicPhase("idle");
      return;
    }
    sessionRef.current = null;
    listeningRef.current = false;
    try {
      const blob = await session.stop();
      await upload(blob);
    } catch (error) {
      toast.error(sttFailToast(0, error instanceof Error ? error.message : "STT failed"));
      setMicPhase("idle");
    }
  }, [setMicPhase, upload]);

  const abort = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    sessionRef.current?.abort();
    sessionRef.current = null;
    listeningRef.current = false;
    setMicPhase("idle");
  }, [setMicPhase]);

  useEffect(() => {
    registerAbort?.(abort);
    return () => registerAbort?.(null);
  }, [abort, registerAbort]);

  const start = useCallback(async () => {
    if (listeningRef.current || sessionRef.current || phase === "transcribing") return;
    listeningRef.current = true;
    setMicPhase("listening");
    try {
      const session = await startMicClip({
        onPermissionRevoked: () => {
          sessionRef.current = null;
          listeningRef.current = false;
          setMicPhase("idle");
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
          if (sessionRef.current === session) void stopAndSend();
        }, 300);
      }
    } catch (error) {
      sessionRef.current = null;
      listeningRef.current = false;
      setMicPhase("idle");
      if (error instanceof DOMException && error.message === MIC_PERMISSION_DENIED) {
        toast.error(MIC_PERMISSION_DENIED);
      } else {
        toast.error(micDeniedMessage(error) || MIC_DENIED_TOAST);
      }
    }
  }, [phase, setMicPhase, stopAndSend]);

  const releasePointer = useCallback((event: ReactPointerEvent<HTMLButtonElement>) => {
    pointerDownRef.current = false;
    if (event.currentTarget.hasPointerCapture(event.pointerId)) {
      event.currentTarget.releasePointerCapture(event.pointerId);
    }
    if (listeningRef.current || sessionRef.current) void stopAndSend();
  }, [stopAndSend]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (phase === "idle") return;
      event.preventDefault();
      abort();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [abort, phase]);

  useEffect(() => () => abort(), [abort]);

  if (locked || !enabled) return null;

  const listening = phase === "listening";
  const transcribing = phase === "transcribing";
  const statusLabel = listening ? MIC_LIVE : transcribing ? MIC_TRANSCRIBING : MIC_IDLE;

  return (
    <Button
      type="button"
      size="icon"
      variant={listening ? "destructive" : "outline"}
      className="relative z-10 size-9 shrink-0"
      disabled={transcribing}
      aria-label={statusLabel}
      data-mic-state={listening ? "live" : transcribing ? "uploading" : "idle"}
      title={
        listening
          ? `${MIC_LIVE} — release to send`
          : transcribing
            ? MIC_TRANSCRIBING
            : `${MIC_IDLE} — hold to talk`
      }
      onPointerDown={(event) => {
        if (transcribing || !enabled) return;
        event.preventDefault();
        pointerDownRef.current = true;
        event.currentTarget.setPointerCapture(event.pointerId);
        void start();
      }}
      onPointerUp={(event) => {
        if (!pointerDownRef.current) return;
        releasePointer(event);
      }}
      onPointerCancel={(event) => {
        if (!pointerDownRef.current) return;
        releasePointer(event);
      }}
      onLostPointerCapture={() => {
        if (!pointerDownRef.current) return;
        pointerDownRef.current = false;
        if (listeningRef.current || sessionRef.current) void stopAndSend();
      }}
    >
      {transcribing ? <LoaderCircle className="size-4 animate-spin" /> : <Mic className="size-4" />}
    </Button>
  );
}
