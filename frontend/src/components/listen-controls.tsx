"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, Pause, Square, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { TtsStatus, TtsWord } from "@/lib/types";

const SPEED_KEY = "storykeep-tts-speed";
const SPEEDS = [0.7, 0.8, 1, 1.2, 1.5, 1.8, 2, 2.2, 2.5, 2.8, 3] as const;

function formatSpeed(rate: number): string {
  return `${rate.toFixed(1)}×`;
}

function readStoredSpeed(): number {
  if (typeof window === "undefined") return 1;
  const raw = window.localStorage.getItem(SPEED_KEY);
  const value = raw ? Number(raw) : 1;
  return SPEEDS.includes(value as (typeof SPEEDS)[number]) ? value : 1;
}

function applyPlaybackRate(audio: HTMLAudioElement, rate: number) {
  audio.playbackRate = rate;
  audio.defaultPlaybackRate = rate;
  if ("preservesPitch" in audio) {
    (audio as HTMLAudioElement & { preservesPitch: boolean }).preservesPitch = true;
  }
}

export function ListenControls({
  articleId,
  hasText,
  onCue,
}: {
  articleId: string;
  hasText: boolean;
  onCue?: (wordIndex: number | null) => void;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const generationRef = useRef(0);
  const wordsRef = useRef<TtsWord[]>([]);
  const wordOffsetRef = useRef(0);
  const cueRafRef = useRef<number | null>(null);
  const lastCueRef = useRef<number | null>(null);
  const [status, setStatus] = useState<TtsStatus | null>(null);
  const [voiceId, setVoiceId] = useState("eve");
  const [speed, setSpeed] = useState(1);
  const speedRef = useRef(1);
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

  useEffect(() => {
    const next = readStoredSpeed();
    setSpeed(next);
    speedRef.current = next;
  }, []);

  const stopCueLoop = useCallback(() => {
    if (cueRafRef.current != null) {
      cancelAnimationFrame(cueRafRef.current);
      cueRafRef.current = null;
    }
  }, []);

  const emitCue = useCallback(
    (index: number | null) => {
      onCue?.(index);
    },
    [onCue],
  );

  const startCueLoop = useCallback(() => {
    stopCueLoop();
    const tick = () => {
      const audio = audioRef.current;
      const words = wordsRef.current;
      if (audio && words.length) {
        const time = audio.currentTime;
        let local = 0;
        for (let i = 0; i < words.length; i += 1) {
          if (time >= words[i].start) local = i;
          if (time < words[i].end) {
            local = i;
            break;
          }
        }
        const next = wordOffsetRef.current + local;
        if (next !== lastCueRef.current) {
          lastCueRef.current = next;
          emitCue(next);
        }
      }
      cueRafRef.current = requestAnimationFrame(tick);
    };
    cueRafRef.current = requestAnimationFrame(tick);
  }, [emitCue, stopCueLoop]);

  const stop = useCallback(() => {
    generationRef.current += 1;
    stopCueLoop();
    lastCueRef.current = null;
    emitCue(null);
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
    wordsRef.current = [];
    setPhase("idle");
    setChunk(0);
    setChunks(1);
  }, [emitCue, stopCueLoop]);

  useEffect(() => {
    generationRef.current += 1;
    setPhase("idle");
    setChunk(0);
    setChunks(1);
    const audio = new Audio();
    applyPlaybackRate(audio, speedRef.current);
    audioRef.current = audio;
    return () => {
      audio.pause();
      audio.onended = null;
      audioRef.current = null;
      if (cueRafRef.current != null) cancelAnimationFrame(cueRafRef.current);
      if (objectUrlRef.current) {
        URL.revokeObjectURL(objectUrlRef.current);
        objectUrlRef.current = null;
      }
      onCue?.(null);
    };
  }, [articleId]);

  const playChunk = useCallback(
    async (index: number, voice: string) => {
      const generation = generationRef.current + 1;
      generationRef.current = generation;
      setPhase("loading");
      try {
        const { blob, chunks: total, words, wordOffset } = await api.articleSpeech(articleId, voice, index);
        if (generation !== generationRef.current) return;
        setChunks(total);
        setChunk(index);
        wordsRef.current = words;
        wordOffsetRef.current = wordOffset;
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
        applyPlaybackRate(audio, speedRef.current);
        await audio.play();
        applyPlaybackRate(audio, speedRef.current);
        if (generation !== generationRef.current) return;
        startCueLoop();
        setPhase("playing");
      } catch (err) {
        if (generation !== generationRef.current) return;
        stop();
        toast.error(err instanceof ApiError ? err.message : "Could not start speech");
      }
    },
    [articleId, startCueLoop, stop],
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
          stopCueLoop();
          setPhase("paused");
        }}>
          <Pause className="size-3.5" />
          Pause
        </Button>
      ) : null}
      {phase === "paused" ? (
        <Button size="sm" variant="outline" onClick={() => {
          const audio = audioRef.current;
          if (audio) applyPlaybackRate(audio, speedRef.current);
          void audio?.play().then(() => {
            startCueLoop();
            setPhase("playing");
          });
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
      <label className="sr-only" htmlFor={`speed-${articleId}`}>
        Speed
      </label>
      <select
        id={`speed-${articleId}`}
        className="h-7 rounded-md border border-border bg-background px-2 text-[0.8rem]"
        value={String(speed)}
        disabled={phase === "loading"}
        onChange={(event) => {
          const next = Number(event.target.value);
          setSpeed(next);
          speedRef.current = next;
          window.localStorage.setItem(SPEED_KEY, String(next));
          const audio = audioRef.current;
          if (audio) applyPlaybackRate(audio, next);
        }}
      >
        {SPEEDS.map((rate) => (
          <option key={rate} value={String(rate)}>
            {formatSpeed(rate)}
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
