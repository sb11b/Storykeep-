"use client";

import { useCallback, useEffect, useRef, useState, type RefObject } from "react";
import { LoaderCircle, Pause, Square, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { cueAheadOfVoice, timestampsMatchChunk, wordIndexAtTime } from "@/lib/tts-cue";
import {
  readStoredTtsSpeed,
  TTS_SPEEDS,
  writeStoredTtsSpeed,
  readStoredTtsVoice,
} from "@/lib/tts-preferences";
import { claimTtsPlayback, releaseTtsPlayback } from "@/lib/tts-session";
import { buildVisibleSpeechScript } from "@/lib/tts-visible";
import type { TtsWord } from "@/lib/types";

function applyPlaybackRate(audio: HTMLAudioElement, rate: number) {
  audio.playbackRate = rate;
  audio.defaultPlaybackRate = rate;
  if ("preservesPitch" in audio) {
    (audio as HTMLAudioElement & { preservesPitch: boolean }).preservesPitch = true;
  }
}

function ttsFailureToast(error: unknown) {
  const status = error instanceof ApiError ? error.status : 0;
  toast.error(`Could not read this reply (HTTP ${status || "error"}).`);
}

export function useGrokMessageListen({
  messageId,
  bodyRef,
  disabled,
  onPlayingChange,
  onCue,
}: {
  messageId: string;
  bodyRef: RefObject<HTMLElement | null>;
  disabled?: boolean;
  onPlayingChange?: (active: boolean) => void;
  onCue?: (wordIndex: number | null) => void;
}) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const generationRef = useRef(0);
  const wordsRef = useRef<TtsWord[]>([]);
  const wordOffsetRef = useRef(0);
  const cueRafRef = useRef<number | null>(null);
  const lastCueRef = useRef<number | null>(null);
  const countsRef = useRef<number[]>([]);
  const timestampsValidRef = useRef(false);
  const stopRef = useRef<() => void>(() => {});
  const [phase, setPhase] = useState<"idle" | "loading" | "playing" | "paused">("idle");
  const [speed, setSpeed] = useState(readStoredTtsSpeed);

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

  const syncCueFromAudio = useCallback(() => {
    if (!timestampsValidRef.current) return;
    const audio = audioRef.current;
    const words = wordsRef.current;
    if (!audio || !words.length) return;
    const local = wordIndexAtTime(words, audio.currentTime);
    if (local == null) return;
    if (cueAheadOfVoice(words, local, audio.currentTime)) return;
    const next = wordOffsetRef.current + local;
    if (next !== lastCueRef.current) {
      lastCueRef.current = next;
      emitCue(next);
    }
  }, [emitCue]);

  const startCueLoop = useCallback(() => {
    stopCueLoop();
    if (!timestampsValidRef.current) return;
    syncCueFromAudio();
    const tick = () => {
      syncCueFromAudio();
      cueRafRef.current = requestAnimationFrame(tick);
    };
    cueRafRef.current = requestAnimationFrame(tick);
  }, [stopCueLoop, syncCueFromAudio]);

  const stop = useCallback(() => {
    generationRef.current += 1;
    stopCueLoop();
    lastCueRef.current = null;
    emitCue(null);
    timestampsValidRef.current = false;
    releaseTtsPlayback(stopRef.current);
    const audio = audioRef.current;
    if (audio) {
      audio.onended = null;
      audio.pause();
      audio.currentTime = 0;
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setPhase("idle");
    onPlayingChange?.(false);
  }, [emitCue, onPlayingChange, stopCueLoop]);

  stopRef.current = stop;

  useEffect(() => {
    const audio = new Audio();
    applyPlaybackRate(audio, readStoredTtsSpeed());
    audioRef.current = audio;
    return () => {
      generationRef.current += 1;
      stopCueLoop();
      audio.onended = null;
      audio.pause();
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      releaseTtsPlayback(stopRef.current);
      audioRef.current = null;
    };
  }, [messageId, stopCueLoop]);

  useEffect(() => {
    onPlayingChange?.(phase === "playing" || phase === "paused" || phase === "loading");
  }, [onPlayingChange, phase]);

  const visibleSpeech = useCallback(() => {
    const root = bodyRef.current;
    if (!root) return null;
    return buildVisibleSpeechScript(root);
  }, [bodyRef]);

  const beginPlayback = useCallback(async () => {
    const payload = visibleSpeech();
    if (!payload?.script.trim()) {
      toast.error("Nothing visible to read in this reply.");
      return;
    }
    claimTtsPlayback(stopRef.current);
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    const voice = readStoredTtsVoice();
    const rate = readStoredTtsSpeed();
    setSpeed(rate);
    setPhase("loading");
    try {
      const data = await api.messageSpeech(messageId, voice, 0, payload.script);
      if (generation !== generationRef.current) return;
      const audio = audioRef.current;
      if (!audio) return;
      if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
      const url = URL.createObjectURL(data.blob);
      objectUrlRef.current = url;
      audio.src = url;
      wordsRef.current = data.words;
      wordOffsetRef.current = data.wordOffset;
      countsRef.current = data.chunkWordCounts.length ? data.chunkWordCounts : [data.words.length || 1];
      timestampsValidRef.current = timestampsMatchChunk(data.words, 0, countsRef.current);
      applyPlaybackRate(audio, rate);
      audio.onended = () => {
        if (generation !== generationRef.current) return;
        stop();
      };
      await audio.play();
      if (generation !== generationRef.current) return;
      setPhase("playing");
      if (timestampsValidRef.current) {
        syncCueFromAudio();
        startCueLoop();
      } else {
        console.warn("[tts-visible] grok reply word timestamps unavailable", {
          ttsWordCount: data.ttsWordCount,
          visibleWordCount: payload.visibleWordCount,
          timedWords: data.words.length,
        });
      }
      if (payload.visibleWordCount !== data.ttsWordCount) {
        console.warn("[tts-visible] grok reply word count mismatch", {
          ttsWordCount: data.ttsWordCount,
          visibleWordCount: payload.visibleWordCount,
        });
      } else {
        console.info("[tts-visible] grok reply", {
          ttsWordCount: data.ttsWordCount,
          visibleWordCount: payload.visibleWordCount,
        });
      }
    } catch (error) {
      if (generation !== generationRef.current) return;
      stop();
      ttsFailureToast(error);
    }
  }, [messageId, startCueLoop, stop, syncCueFromAudio, visibleSpeech]);

  const listen = useCallback(() => {
    if (disabled) return;
    if (phase === "paused") {
      const audio = audioRef.current;
      if (!audio) return;
      claimTtsPlayback(stopRef.current);
      applyPlaybackRate(audio, speed);
      void audio.play().then(() => {
        setPhase("playing");
        startCueLoop();
      });
      return;
    }
    if (phase === "idle") void beginPlayback();
  }, [beginPlayback, disabled, phase, speed, startCueLoop]);

  const pause = useCallback(() => {
    if (phase !== "playing") return;
    audioRef.current?.pause();
    stopCueLoop();
    setPhase("paused");
  }, [phase, stopCueLoop]);

  const changeSpeed = useCallback(
    (rate: number) => {
      writeStoredTtsSpeed(rate);
      setSpeed(rate);
      const audio = audioRef.current;
      if (audio) applyPlaybackRate(audio, rate);
    },
    [],
  );

  return {
    phase,
    speed,
    listen,
    pause,
    stop,
    changeSpeed,
    isActive: phase !== "idle",
  };
}

export function GrokListenBar({
  phase,
  disabled,
  speed,
  onListen,
  onPause,
  onStop,
  onSpeedChange,
}: {
  phase: "idle" | "loading" | "playing" | "paused";
  disabled?: boolean;
  speed: number;
  onListen: () => void;
  onPause: () => void;
  onStop: () => void;
  onSpeedChange: (rate: number) => void;
}) {
  const listenLabel = phase === "paused" ? "Resume" : "Listen";
  const listenDisabled = disabled || phase === "loading" || phase === "playing";
  const pauseDisabled = phase !== "playing";
  const stopDisabled = phase === "idle" || phase === "loading";

  return (
    <div className="flex flex-wrap items-center gap-1 rounded-md border border-border/60 bg-background/80 px-1.5 py-1 text-xs">
      <Button size="xs" variant="outline" disabled={listenDisabled} onClick={onListen}>
        {phase === "loading" ? <LoaderCircle className="size-3 animate-spin" /> : <Volume2 className="size-3" />}
        {phase === "loading" ? "Preparing…" : listenLabel}
      </Button>
      <Button size="xs" variant="outline" disabled={pauseDisabled} onClick={onPause}>
        <Pause className="size-3" />
        Pause
      </Button>
      <Button size="xs" variant="outline" disabled={stopDisabled} onClick={onStop}>
        <Square className="size-3" />
        Stop
      </Button>
      <select
        aria-label="Playback speed"
        className="h-7 rounded-md border border-input bg-background px-1.5 text-[0.72rem] outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
        value={speed}
        disabled={disabled || phase === "loading"}
        onChange={(event) => onSpeedChange(Number(event.target.value))}
      >
        {TTS_SPEEDS.map((rate) => (
          <option key={rate} value={rate}>
            {rate === 1 ? "1×" : `${rate}×`}
          </option>
        ))}
      </select>
    </div>
  );
}
