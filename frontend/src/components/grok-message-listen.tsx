"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { LoaderCircle, Pause, Square, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { ApiError, api } from "@/lib/api";
import { cueAheadOfVoice, timestampsMatchChunk, wordIndexAtTime } from "@/lib/tts-cue";
import { readStoredTtsSpeed, readStoredTtsVoice } from "@/lib/tts-preferences";
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

export function useGrokMessageListen({
  messageId,
  bodyRef,
  disabled,
  onPlayingChange,
  onCue,
}: {
  messageId: string;
  bodyRef: React.RefObject<HTMLElement | null>;
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
  const [phase, setPhase] = useState<"idle" | "loading" | "playing" | "paused">("idle");

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
    releaseTtsPlayback(stop);
    const audio = audioRef.current;
    if (audio) {
      audio.onended = null;
      audio.pause();
    }
    if (objectUrlRef.current) {
      URL.revokeObjectURL(objectUrlRef.current);
      objectUrlRef.current = null;
    }
    setPhase("idle");
    onPlayingChange?.(false);
  }, [emitCue, onPlayingChange, stopCueLoop]);

  useEffect(() => {
    const audio = new Audio();
    applyPlaybackRate(audio, readStoredTtsSpeed());
    audioRef.current = audio;
    return () => {
      stop();
      audioRef.current = null;
    };
  }, [messageId, stop]);

  useEffect(() => {
    onPlayingChange?.(phase !== "idle" && phase !== "loading");
  }, [onPlayingChange, phase]);

  const visibleSpeech = useCallback(() => {
    const root = bodyRef.current;
    if (!root) return null;
    return buildVisibleSpeechScript(root);
  }, [bodyRef]);

  const play = useCallback(async () => {
    if (disabled) return;
    const payload = visibleSpeech();
    if (!payload?.script.trim()) {
      toast.error("Nothing visible to read in this message.");
      return;
    }
    claimTtsPlayback(stop);
    const generation = generationRef.current + 1;
    generationRef.current = generation;
    const voice = readStoredTtsVoice();
    const speed = readStoredTtsSpeed();
    setPhase("loading");
    onPlayingChange?.(true);
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
      applyPlaybackRate(audio, speed);
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
      toast.error(error instanceof ApiError ? error.message : "Could not read that reply aloud");
    }
  }, [disabled, messageId, onPlayingChange, startCueLoop, stop, syncCueFromAudio, visibleSpeech]);

  const toggle = useCallback(() => {
    if (phase === "playing") {
      audioRef.current?.pause();
      stopCueLoop();
      setPhase("paused");
      return;
    }
    if (phase === "paused") {
      const audio = audioRef.current;
      if (audio) {
        applyPlaybackRate(audio, readStoredTtsSpeed());
        void audio.play().then(() => {
          setPhase("playing");
          startCueLoop();
        });
      }
      return;
    }
    if (phase === "idle") void play();
  }, [phase, play, startCueLoop, stopCueLoop]);

  return { phase, toggle, stop, isActive: phase !== "idle" };
}

export function GrokListenButton({
  phase,
  disabled,
  onClick,
}: {
  phase: "idle" | "loading" | "playing" | "paused";
  disabled?: boolean;
  onClick: () => void;
}) {
  if (phase === "loading") {
    return (
      <Button size="xs" variant="outline" disabled>
        <LoaderCircle className="size-3 animate-spin" />
        Preparing…
      </Button>
    );
  }
  if (phase === "playing") {
    return (
      <Button size="xs" variant="outline" onClick={onClick}>
        <Pause className="size-3" />
        Pause
      </Button>
    );
  }
  return (
    <Button size="xs" variant="outline" disabled={disabled} onClick={onClick}>
      <Volume2 className="size-3" />
      {phase === "paused" ? "Resume" : "Listen"}
    </Button>
  );
}

export function GrokListenStopBar({ onStop }: { onStop: () => void }) {
  return (
    <div className="sticky top-0 z-10 flex shrink-0 items-center justify-between gap-2 border-b bg-primary/10 px-3 py-1.5 text-xs">
      <span className="text-muted-foreground">Reading aloud — Esc to stop</span>
      <Button size="xs" variant="secondary" onClick={onStop}>
        <Square className="size-3" />
        Stop
      </Button>
    </div>
  );
}
