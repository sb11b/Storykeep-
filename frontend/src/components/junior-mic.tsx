import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, Mic } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { appendSpoken } from "@/lib/stt-buffer";
import { MIN_CLIP_BYTES, startMicClip, sttFailToast, type MicClipSession } from "@/lib/junior-stt";
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
  const [listening, setListening] = useState(false);
  const [uploading, setUploading] = useState(false);
  const sessionRef = useRef<MicClipSession | null>(null);
  const listeningRef = useRef(false);
  listeningRef.current = listening;

  const upload = useCallback(
    async (blob: Blob) => {
      if (blob.size < MIN_CLIP_BYTES) {
        toast.error(sttFailToast(400, "empty blob"));
        setUploading(false);
        setListening(false);
        return;
      }
      setUploading(true);
      setListening(false);
      try {
        const result = await api.transcribeStt(blob);
        const piece = (result.text || "").trim();
        if (!piece) {
          toast.error("STT failed (empty transcript)");
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
        setUploading(false);
        setListening(false);
      }
    },
    [getDraft, onTranscript],
  );

  const stopAndSend = useCallback(async () => {
    const session = sessionRef.current;
    sessionRef.current = null;
    listeningRef.current = false;
    setListening(false);
    if (!session) {
      setUploading(false);
      return;
    }
    try {
      const blob = await session.stop();
      await upload(blob);
    } catch (error) {
      toast.error(sttFailToast(0, error instanceof Error ? error.message : "STT failed"));
      setUploading(false);
      setListening(false);
    }
  }, [upload]);

  const abort = useCallback(() => {
    sessionRef.current?.abort();
    sessionRef.current = null;
    listeningRef.current = false;
    setListening(false);
    setUploading(false);
  }, []);

  const start = useCallback(async () => {
    if (listeningRef.current || sessionRef.current) return;
    listeningRef.current = true;
    setListening(true);
    try {
      const session = await startMicClip({
        onPermissionRevoked: () => {
          sessionRef.current = null;
          listeningRef.current = false;
          setListening(false);
          setUploading(false);
          toast.error(MIC_DENIED_TOAST);
        },
      });
      if (!listeningRef.current) {
        session.abort();
        return;
      }
      sessionRef.current = session;
    } catch (error) {
      sessionRef.current = null;
      listeningRef.current = false;
      setListening(false);
      toast.error(micDeniedMessage(error) || MIC_DENIED_TOAST);
    }
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape") return;
      if (!listeningRef.current) return;
      event.preventDefault();
      abort();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [abort]);

  useEffect(() => () => abort(), [abort]);

  if (locked || !enabled) return null;

  return (
    <Button
      type="button"
      size="icon"
      variant={listening ? "destructive" : "outline"}
      className="relative z-10 size-9 shrink-0"
      disabled={uploading}
      aria-label={listening ? MIC_LIVE : uploading ? "Transcribing" : MIC_IDLE}
      data-mic-state={listening ? "live" : uploading ? "uploading" : "idle"}
      title={listening ? `${MIC_LIVE} — tap to stop` : `${MIC_IDLE} — tap to talk, tap again to insert`}
      onMouseDown={(event) => event.preventDefault()}
      onClick={() => {
        if (uploading) return;
        if (listening) {
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
