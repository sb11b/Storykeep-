"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, Pause, Square, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { TtsStatus } from "@/lib/types";

export function ListenControls({
  articleId,
  hasText,
}: {
  articleId: string;
  hasText: boolean;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const generationRef = useRef(0);
  const [status, setStatus] = useState<TtsStatus | null>(null);
  const [voiceId, setVoiceId] = useState("eve");
  const [phase, setPhase] = useState<"idle" | "loading" | "playing" | "paused">("idle");
  const [chunk, setChunk] = useState(0);
  const [chunks, setChunks] = useState(1);

  useEffect(() => {
    let cancelled = false;
    api
      .tts()
      .then((next) => {
        if (cancelled) return;
        setStatus(next);
        if (next.voices[0]?.voice_id) setVoiceId(next.voices[0].voice_id);
      })
      .catch(() => {
        if (!cancelled) setStatus({ enabled: false, provider: "xai", voices: [] });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  const stop = useCallback(() => {
    generationRef.current += 1;
    const audio = audioRef.current;
    if (audio) {
      audio.onended = null;
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setPhase("idle");
    setChunk(0);
    setChunks(1);
  }, []);

  useEffect(() => {
    generationRef.current += 1;
    setPhase("idle");
    setChunk(0);
    setChunks(1);
    const audio = new Audio();
    audioRef.current = audio;
    return () => {
      audio.pause();
      audio.onended = null;
      audioRef.current = null;
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
    };
  }, [articleId]);

  const playChunk = useCallback(
    async (index: number, voice: string) => {
      const generation = generationRef.current + 1;
      generationRef.current = generation;
      setPhase("loading");
      try {
        const { blob, chunks: total } = await api.articleSpeech(articleId, voice, index);
        if (generation !== generationRef.current) return;
        setChunks(total);
        setChunk(index);
        if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
        const url = URL.createObjectURL(blob);
        objectUrlRef.current = url;
        const audio = audioRef.current;
        if (!audio) return;
        audio.onended = () => {
          if (generation !== generationRef.current) return;
          if (index + 1 < total) {
            void playChunk(index + 1, voice);
          } else {
            stop();
          }
        };
        audio.src = url;
        await audio.play();
        if (generation !== generationRef.current) return;
        setPhase("playing");
      } catch (err) {
        if (generation !== generationRef.current) return;
        stop();
        toast.error(err instanceof ApiError ? err.message : "Could not start speech");
      }
    },
    [articleId, stop],
  );

  return (
    <div className="flex flex-wrap items-center gap-2">
      {phase === "idle" ? (
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            if (!hasText) {
              toast.error("Extract the full text first, then listen.");
              return;
            }
            void playChunk(0, voiceId);
          }}
        >
          <Volume2 className="size-3.5" />
          Listen
        </Button>
      ) : null}
      {phase === "loading" ? (
        <Button size="sm" variant="outline" disabled>
          <LoaderCircle className="size-3.5 animate-spin" />
          Preparing speech…
        </Button>
      ) : null}
      {phase === "playing" ? (
        <Button size="sm" variant="outline" onClick={() => {
          audioRef.current?.pause();
          setPhase("paused");
        }}>
          <Pause className="size-3.5" />
          Pause
        </Button>
      ) : null}
      {phase === "paused" ? (
        <Button size="sm" variant="outline" onClick={() => {
          void audioRef.current?.play().then(() => setPhase("playing"));
        }}>
          <Volume2 className="size-3.5" />
          Resume
        </Button>
      ) : null}
      {phase !== "idle" && phase !== "loading" ? (
        <Button size="sm" variant="ghost" onClick={stop}>
          <Square className="size-3" />
          Stop
        </Button>
      ) : null}
      <label className="sr-only" htmlFor={`voice-${articleId}`}>
        Voice
      </label>
      <select
        id={`voice-${articleId}`}
        className={cn(
          "h-7 rounded-md border border-border bg-background px-2 text-[0.8rem]",
          phase !== "idle" && "opacity-70",
        )}
        value={voiceId}
        disabled={phase === "loading"}
        onChange={(event) => {
          const next = event.target.value;
          setVoiceId(next);
          if (phase !== "idle") void playChunk(0, next);
        }}
      >
        {(status?.voices.length ? status.voices : [{ voice_id: "eve", name: "Eve" }]).map((voice) => (
          <option key={voice.voice_id} value={voice.voice_id}>
            {voice.name}
          </option>
        ))}
      </select>
      {phase !== "idle" && chunks > 1 ? (
        <span className="text-xs text-muted-foreground">
          Part {chunk + 1} of {chunks}
        </span>
      ) : null}
    </div>
  );
}
