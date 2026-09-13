"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, Pause, Square, Volume2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api";
import { showTtsErrorToast } from "@/lib/tts-error-toast";
import { cueAheadOfVoice, timestampsMatchChunk, wordIndexAtTime } from "@/lib/tts-cue";
import {
  readStoredTtsSpeed,
  TTS_SPEEDS,
  writeStoredTtsSpeed,
  readStoredTtsVoice,
} from "@/lib/tts-preferences";
import { claimTtsPlayback, releaseTtsPlayback } from "@/lib/tts-session";
import type { TtsWord } from "@/lib/types";

type ChunkPayload = Awaited<ReturnType<typeof api.messageSpeech>>;

function applyPlaybackRate(audio: HTMLAudioElement, rate: number) {
  audio.playbackRate = rate;
  audio.defaultPlaybackRate = rate;
  if ("preservesPitch" in audio) {
    (audio as HTMLAudioElement & { preservesPitch: boolean }).preservesPitch = true;
  }
}

export function useGrokMessageListen({
  messageId,
  resolveScript,
  voiceId,
  disabled,
  onPlayingChange,
  onCue,
}: {
  messageId: string;
  /** Reads the live reply text. Called again if the script is ever lost. */
  resolveScript: () => string;
  voiceId: string;
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
  const scriptRef = useRef("");
  const loadedChunkRef = useRef<number | null>(null);
  const loadedVoiceRef = useRef<string | null>(null);
  const totalChunksRef = useRef(1);
  const chunkCacheRef = useRef<Map<string, ChunkPayload>>(new Map());
  const voiceRef = useRef(voiceId);
  const speedRef = useRef(readStoredTtsSpeed());
  const stopRef = useRef<() => void>(() => {});
  const playChunkRef = useRef<(index: number, voice: string) => Promise<void>>(async () => {});
  const [phase, setPhase] = useState<"idle" | "loading" | "playing" | "paused">("idle");
  const [speed, setSpeed] = useState(readStoredTtsSpeed);

  useEffect(() => {
    voiceRef.current = voiceId;
  }, [voiceId]);

  useEffect(() => {
    speedRef.current = speed;
  }, [speed]);

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

  const markTimestampsUnavailable = useCallback(() => {
    timestampsValidRef.current = false;
    stopCueLoop();
    lastCueRef.current = null;
    emitCue(null);
  }, [emitCue, stopCueLoop]);

  const applyTimestampValidation = useCallback(
    (words: TtsWord[], chunkIndex: number, chunkWordCounts: number[]) => {
      const valid = timestampsMatchChunk(words, chunkIndex, chunkWordCounts);
      timestampsValidRef.current = valid;
      if (!valid) {
        markTimestampsUnavailable();
        return false;
      }
      return true;
    },
    [markTimestampsUnavailable],
  );

  const syncCueFromAudio = useCallback(() => {
    if (!timestampsValidRef.current) return;
    const audio = audioRef.current;
    const words = wordsRef.current;
    if (!audio || !words.length) return;
    const currentTime = audio.currentTime;
    const local = wordIndexAtTime(words, currentTime);
    if (local == null) return;
    if (cueAheadOfVoice(words, local, currentTime)) return;
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

  const resetLoaded = useCallback(() => {
    loadedChunkRef.current = null;
    loadedVoiceRef.current = null;
    countsRef.current = [];
    totalChunksRef.current = 1;
    scriptRef.current = "";
    chunkCacheRef.current.clear();
  }, []);

  const stop = useCallback(() => {
    generationRef.current += 1;
    stopCueLoop();
    lastCueRef.current = null;
    emitCue(null);
    markTimestampsUnavailable();
    releaseTtsPlayback(stopRef.current);
    const audio = audioRef.current;
    if (audio) {
      audio.onended = null;
      audio.onloadedmetadata = null;
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    resetLoaded();
    setPhase("idle");
    onPlayingChange?.(false);
  }, [emitCue, markTimestampsUnavailable, onPlayingChange, resetLoaded, stopCueLoop]);

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

  const chunkCacheKey = useCallback((index: number, voice: string) => `${messageId}:${voice}:${index}`, [messageId]);

  const loadChunk = useCallback(
    async (index: number, voice: string) => {
      const cached = chunkCacheRef.current.get(chunkCacheKey(index, voice));
      if (cached) return cached;
      // A cleared script is a bug on our side, not an empty reply: read it again.
      const script = scriptRef.current.trim() || resolveScript().trim();
      if (!script) {
        throw new Error("That reply is still empty — nothing to read yet.");
      }
      scriptRef.current = script;
      console.log("larry-tts", { stage: "POST /tts", chars: script.length, chunk: index });
      const data = await api.messageSpeech(messageId, voice, index, script, true);
      chunkCacheRef.current.set(chunkCacheKey(index, voice), data);
      if (data.chunkWordCounts.length) countsRef.current = data.chunkWordCounts;
      return data;
    },
    [chunkCacheKey, messageId, resolveScript],
  );

  const prefetchChunk = useCallback(
    (index: number, voice: string, total: number) => {
      if (index >= total) return;
      if (chunkCacheRef.current.has(chunkCacheKey(index, voice))) return;
      void loadChunk(index, voice).catch(() => {
        /* prefetch failure is non-fatal */
      });
    },
    [chunkCacheKey, loadChunk],
  );

  const playChunk = useCallback(
    async (index: number, voice: string) => {
      claimTtsPlayback(stopRef.current);
      const generation = generationRef.current + 1;
      generationRef.current = generation;
      const audio = audioRef.current;
      if (!audio) return;

      const attachEnded = (total: number) => {
        audio.onended = () => {
          if (generation !== generationRef.current) return;
          if (index + 1 < total) {
            void playChunkRef.current(index + 1, voice);
          } else {
            stop();
          }
        };
      };

      const seekAndPlay = async (
        data: ChunkPayload,
        chunkIndex: number,
      ) => {
        wordsRef.current = data.words;
        wordOffsetRef.current = data.wordOffset;
        const counts = data.chunkWordCounts.length ? data.chunkWordCounts : countsRef.current;
        applyTimestampValidation(data.words, chunkIndex, counts);
        applyPlaybackRate(audio, speedRef.current);
        audio.currentTime = 0;
        await audio.play();
        applyPlaybackRate(audio, speedRef.current);
        if (generation !== generationRef.current) return;
        setPhase("playing");
        if (timestampsValidRef.current) {
          syncCueFromAudio();
          startCueLoop();
        }
      };

      const alreadyLoaded =
        loadedChunkRef.current === index && loadedVoiceRef.current === voice && Boolean(audio.src);
      if (alreadyLoaded && wordsRef.current.length) {
        attachEnded(totalChunksRef.current);
        const cached = chunkCacheRef.current.get(chunkCacheKey(index, voice));
        if (cached) {
          await seekAndPlay(cached, index);
        }
        return;
      }

      setPhase("loading");
      try {
        const data = await loadChunk(index, voice);
        if (generation !== generationRef.current) return;
        totalChunksRef.current = data.chunks;
        attachEnded(data.chunks);
        if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
        const url = URL.createObjectURL(data.blob);
        objectUrlRef.current = url;
        audio.src = url;
        loadedChunkRef.current = index;
        loadedVoiceRef.current = voice;
        await seekAndPlay(data, index);
        prefetchChunk(index + 1, voice, data.chunks);
      } catch (error) {
        if (generation !== generationRef.current) return;
        stop();
        showTtsErrorToast(error);
      }
    },
    [
      applyTimestampValidation,
      chunkCacheKey,
      loadChunk,
      prefetchChunk,
      startCueLoop,
      stop,
      syncCueFromAudio,
    ],
  );

  playChunkRef.current = playChunk;

  const beginPlayback = useCallback(async () => {
    const script = resolveScript().trim();
    console.log("larry-tts", { stage: "begin", chars: script.length, sample: script.slice(0, 80) });
    if (!script) {
      showTtsErrorToast(new Error("That reply is still empty — nothing to read yet."));
      return;
    }
    // resetLoaded() clears scriptRef, so pin the script after the reset.
    resetLoaded();
    scriptRef.current = script;
    const rate = readStoredTtsSpeed();
    setSpeed(rate);
    speedRef.current = rate;
    const voice = voiceRef.current || readStoredTtsVoice();
    await playChunk(0, voice);
  }, [playChunk, resetLoaded, resolveScript]);

  const listen = useCallback(() => {
    if (disabled) return;
    if (phase === "paused") {
      const audio = audioRef.current;
      if (!audio) return;
      claimTtsPlayback(stopRef.current);
      applyPlaybackRate(audio, speedRef.current);
      void audio.play().then(() => {
        setPhase("playing");
        startCueLoop();
      });
      return;
    }
    if (phase === "idle") void beginPlayback();
  }, [beginPlayback, disabled, phase, startCueLoop]);

  const pause = useCallback(() => {
    if (phase !== "playing") return;
    audioRef.current?.pause();
    stopCueLoop();
    setPhase("paused");
  }, [phase, stopCueLoop]);

  const changeSpeed = useCallback((rate: number) => {
    writeStoredTtsSpeed(rate);
    setSpeed(rate);
    speedRef.current = rate;
    const audio = audioRef.current;
    if (audio) applyPlaybackRate(audio, rate);
  }, []);

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
  voiceId,
  voices,
  onListen,
  onPause,
  onStop,
  onSpeedChange,
  onVoiceChange,
  compact,
}: {
  phase: "idle" | "loading" | "playing" | "paused";
  disabled?: boolean;
  speed: number;
  voiceId?: string;
  voices?: { voice_id: string; name: string }[];
  onListen: () => void;
  onPause: () => void;
  onStop: () => void;
  onSpeedChange: (rate: number) => void;
  onVoiceChange?: (voiceId: string) => void;
  compact?: boolean;
}) {
  const listenLabel = phase === "paused" ? "Resume" : "Listen";
  const listenDisabled = disabled || phase === "loading" || phase === "playing";
  const pauseDisabled = phase !== "playing";
  const stopDisabled = phase === "idle" || phase === "loading";

  const voiceOptions = voices?.length ? voices : [{ voice_id: "eve", name: "Eve" }];

  return (
    <div
      className={
        compact
          ? "flex flex-wrap items-center gap-1 text-xs"
          : "sticky top-0 z-10 flex flex-wrap items-center gap-1 border-b bg-popover/95 px-2 py-1.5 text-xs backdrop-blur-sm"
      }
    >
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
        aria-label="Voice"
        className="h-7 min-w-[5.5rem] rounded-md border border-input bg-background px-1.5 text-[0.72rem] outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:opacity-50"
        value={voiceId ?? voiceOptions[0]!.voice_id}
        disabled={disabled || phase === "loading"}
        onChange={(event) => onVoiceChange?.(event.target.value)}
      >
        {voiceOptions.map((voice) => (
          <option key={voice.voice_id} value={voice.voice_id}>
            {voice.name}
          </option>
        ))}
      </select>
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
