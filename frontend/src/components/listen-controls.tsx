"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { LoaderCircle, Pause, Square, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { ApiError, api } from "@/lib/api";
import { cn } from "@/lib/utils";
import type { TtsStatus, TtsWord } from "@/lib/types";

const SPEED_KEY = "storykeep-tts-speed";
const SPEEDS = [0.7, 0.8, 1, 1.2, 1.5, 1.8, 2, 2.2, 2.5, 2.8, 3] as const;

type SpeechPayload = {
  blob: Blob;
  chunks: number;
  wordOffset: number;
  chunkWordCounts: number[];
  duration: number | null;
  words: TtsWord[];
  contentHash?: string;
};

const speechMemory = new Map<string, SpeechPayload>();

function memoryKey(
  articleId: string,
  voice: string,
  chunk: number,
  section: string | null,
  includeNotes: boolean,
  contentHash: string,
) {
  return `${articleId}:${contentHash || "pending"}:${voice}:${section || "full"}:${includeNotes ? "notes" : "body"}:${chunk}`;
}

function rememberSpeech(key: string, data: SpeechPayload) {
  speechMemory.set(key, data);
  if (speechMemory.size > 32) {
    const oldest = speechMemory.keys().next().value;
    if (oldest) speechMemory.delete(oldest);
  }
}

export type ListenControlsHandle = {
  togglePlay: () => void;
  playFromWord: (wordIndex: number) => void;
  listenFromHere: () => void;
  stop: () => void;
  isActive: () => boolean;
};

function formatSpeed(rate: number): string {
  return `${rate.toFixed(1)}×`;
}

function readStoredSpeed(): number {
  if (typeof window === "undefined") return 1;
  const raw = window.localStorage.getItem(SPEED_KEY);
  const value = raw ? Number(raw) : 1;
  return SPEEDS.includes(value as (typeof SPEEDS)[number]) ? value : 1;
}

function resumeKey(articleId: string) {
  return `storykeep-tts-resume:${articleId}`;
}

function writeResume(articleId: string, wordIndex: number | null) {
  if (typeof window === "undefined") return;
  if (wordIndex == null) {
    window.localStorage.removeItem(resumeKey(articleId));
    return;
  }
  window.localStorage.setItem(resumeKey(articleId), JSON.stringify({ wordIndex }));
}

function applyPlaybackRate(audio: HTMLAudioElement, rate: number) {
  audio.playbackRate = rate;
  audio.defaultPlaybackRate = rate;
  if ("preservesPitch" in audio) {
    (audio as HTMLAudioElement & { preservesPitch: boolean }).preservesPitch = true;
  }
}

function chunkForWord(counts: number[], wordIndex: number) {
  if (!counts.length) return { chunk: 0, local: 0 };
  let acc = 0;
  for (let i = 0; i < counts.length; i += 1) {
    const next = acc + counts[i];
    if (wordIndex < next) return { chunk: i, local: Math.max(0, wordIndex - acc) };
    acc = next;
  }
  return { chunk: counts.length - 1, local: Math.max(0, counts[counts.length - 1] - 1) };
}

export const ListenControls = forwardRef<
  ListenControlsHandle,
  {
    articleId: string;
    hasText: boolean;
    includeNotes?: boolean;
    noteMode?: boolean;
    onCue?: (wordIndex: number | null) => void;
    getCaretWord?: () => number | null;
  }
>(function ListenControls({ articleId, hasText, includeNotes = false, noteMode = false, onCue, getCaretWord }, ref) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const objectUrlRef = useRef<string | null>(null);
  const generationRef = useRef(0);
  const wordsRef = useRef<TtsWord[]>([]);
  const wordOffsetRef = useRef(0);
  const cueRafRef = useRef<number | null>(null);
  const lastCueRef = useRef<number | null>(null);
  const loadedChunkRef = useRef<number | null>(null);
  const loadedVoiceRef = useRef<string | null>(null);
  const countsRef = useRef<number[]>([]);
  const sectionRef = useRef<string | null>(null);
  const confirmRef = useRef(false);
  const [planOpen, setPlanOpen] = useState(false);
  const [plan, setPlan] = useState<{ chars: number; sections: { id: string; title: string; chars: number }[] } | null>(null);
  const pendingWordRef = useRef(0);
  const includeNotesRef = useRef(includeNotes);
  const contentHashRef = useRef("");
  const [status, setStatus] = useState<TtsStatus | null>(null);
  const [voiceId, setVoiceId] = useState("eve");
  const [speed, setSpeed] = useState(1);
  const speedRef = useRef(1);
  const [phase, setPhase] = useState<"idle" | "loading" | "playing" | "paused">("idle");
  const phaseRef = useRef(phase);
  const [chunk, setChunk] = useState(0);
  const [chunks, setChunks] = useState(1);
  const voiceRef = useRef(voiceId);

  useEffect(() => {
    phaseRef.current = phase;
  }, [phase]);

  useEffect(() => {
    voiceRef.current = voiceId;
  }, [voiceId]);

  useEffect(() => {
    includeNotesRef.current = includeNotes;
  }, [includeNotes]);

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

  const persistCue = useCallback(() => {
    writeResume(articleId, lastCueRef.current);
  }, [articleId]);

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

  const stop = useCallback(
    (clearResume = false) => {
      generationRef.current += 1;
      stopCueLoop();
      if (clearResume) {
        writeResume(articleId, null);
        void api.releaseTtsAudio(articleId, voiceRef.current).catch(() => undefined);
      }
      else persistCue();
      lastCueRef.current = null;
      emitCue(null);
      const audio = audioRef.current;
      if (audio) {
        audio.onended = null;
        audio.pause();
      }
      loadedChunkRef.current = null;
      loadedVoiceRef.current = null;
      wordsRef.current = [];
      setPhase("idle");
      setChunk(0);
      setChunks(1);
    },
    [articleId, emitCue, persistCue, stopCueLoop],
  );

  useEffect(() => {
    generationRef.current += 1;
    setPhase("idle");
    setChunk(0);
    setChunks(1);
    loadedChunkRef.current = null;
    loadedVoiceRef.current = null;
    countsRef.current = [];
    sectionRef.current = null;
    confirmRef.current = false;
    contentHashRef.current = "";
    const audio = new Audio();
    applyPlaybackRate(audio, speedRef.current);
    audioRef.current = audio;
    return () => {
      persistCue();
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
  }, [articleId, includeNotes, persistCue]);

  const loadChunk = useCallback(
    async (index: number, voice: string) => {
      const section = sectionRef.current;
      const key = memoryKey(articleId, voice, index, section, includeNotesRef.current, contentHashRef.current);
      const hit = speechMemory.get(key);
      if (hit) return hit;
      const data = await api.articleSpeech(articleId, voice, index, {
        confirm: confirmRef.current,
        section,
        includeNotes: includeNotesRef.current,
      });
      if (data.contentHash) contentHashRef.current = data.contentHash;
      rememberSpeech(memoryKey(articleId, voice, index, section, includeNotesRef.current, contentHashRef.current), data);
      if (data.chunkWordCounts.length) countsRef.current = data.chunkWordCounts;
      return data;
    },
    [articleId, includeNotes],
  );

  const playChunk = useCallback(
    async (index: number, voice: string, seekLocal: number | null = null) => {
      const generation = generationRef.current + 1;
      generationRef.current = generation;
      const audio = audioRef.current;
      if (!audio) return;

      const attachEnded = (total: number) => {
        audio.onended = () => {
          if (generation !== generationRef.current) return;
          if (index + 1 < total) {
            void playChunk(index + 1, voice, null);
          } else {
            stop(true);
          }
        };
      };

      const seekAndPlay = async (words: TtsWord[], wordOffset: number) => {
        wordsRef.current = words;
        wordOffsetRef.current = wordOffset;
        applyPlaybackRate(audio, speedRef.current);
        const applySeek = () => {
          if (seekLocal != null && words[seekLocal]) {
            audio.currentTime = words[seekLocal].start;
          } else if (seekLocal == null) {
            audio.currentTime = 0;
          }
        };
        audio.onloadedmetadata = applySeek;
        applySeek();
        await audio.play();
        applySeek();
        applyPlaybackRate(audio, speedRef.current);
        if (generation !== generationRef.current) return;
        startCueLoop();
        setPhase("playing");
        if (seekLocal != null) {
          lastCueRef.current = wordOffset + seekLocal;
          emitCue(lastCueRef.current);
        }
      };

      const alreadyLoaded = loadedChunkRef.current === index && loadedVoiceRef.current === voice && Boolean(audio.src);
      if (alreadyLoaded && wordsRef.current.length) {
        const cached = speechMemory.get(
          memoryKey(articleId, voice, index, sectionRef.current, includeNotesRef.current, contentHashRef.current),
        );
        const total = cached?.chunks ?? 1;
        attachEnded(total);
        setChunk(index);
        setChunks(total);
        await seekAndPlay(wordsRef.current, wordOffsetRef.current);
        return;
      }

      setPhase("loading");
      try {
        const data = await loadChunk(index, voice);
        if (generation !== generationRef.current) return;
        setChunks(data.chunks);
        setChunk(index);
        attachEnded(data.chunks);
        if (objectUrlRef.current) URL.revokeObjectURL(objectUrlRef.current);
        const url = URL.createObjectURL(data.blob);
        objectUrlRef.current = url;
        audio.src = url;
        loadedChunkRef.current = index;
        loadedVoiceRef.current = voice;
        await seekAndPlay(data.words, data.wordOffset);
        if (index + 1 < data.chunks) {
          void loadChunk(index + 1, voice);
        }
      } catch (err) {
        if (generation !== generationRef.current) return;
        stop();
        toast.error(err instanceof ApiError ? err.message : "Could not start speech");
      }
    },
    [articleId, emitCue, loadChunk, startCueLoop, stop],
  );

  const startAtWord = useCallback(
    async (wordIndex: number, opts?: { confirm?: boolean; section?: string | null }) => {
      if (!hasText) {
        toast.error(noteMode ? "This note has no text to read." : "Extract the full text first, then listen.");
        return;
      }
      const voice = voiceRef.current;
      if (opts?.confirm) confirmRef.current = true;
      if (opts?.section !== undefined) {
        sectionRef.current = opts.section;
        countsRef.current = [];
      }
      if (!confirmRef.current && !sectionRef.current) {
        try {
          const nextPlan = await api.ttsPlan(articleId, voice, { includeNotes: includeNotesRef.current });
          if (nextPlan.content_hash) contentHashRef.current = nextPlan.content_hash;
          if (nextPlan.long) {
            pendingWordRef.current = wordIndex;
            setPlan(nextPlan);
            setPlanOpen(true);
            return;
          }
        } catch {
          /* play anyway; the speech endpoint will error if needed */
        }
      }
      let counts = countsRef.current;
      if (!counts.length) {
        const first = await loadChunk(0, voice);
        counts = first.chunkWordCounts.length ? first.chunkWordCounts : [first.words.length || 1];
        countsRef.current = counts;
      }
      const { chunk: target, local } = chunkForWord(counts, Math.max(0, wordIndex));
      void playChunk(target, voice, local);
    },
    [articleId, hasText, includeNotes, loadChunk, noteMode, playChunk],
  );

  const listenFromHere = useCallback(() => {
    if (!hasText) {
      toast.error(noteMode ? "This note has no text to read." : "Extract the full text first, then listen.");
      return;
    }
    const word = getCaretWord?.();
    void startAtWord(word == null ? 0 : word);
  }, [getCaretWord, hasText, noteMode, startAtWord]);

  const togglePlay = useCallback(() => {
    if (!hasText) {
      toast.error(noteMode ? "This note has no text to read." : "Extract the full text first, then listen.");
      return;
    }
    if (phaseRef.current !== "idle") {
      stop();
      return;
    }
    void startAtWord(0);
  }, [hasText, noteMode, startAtWord, stop]);

  useImperativeHandle(
    ref,
    () => ({
      togglePlay,
      playFromWord: (wordIndex: number) => {
        void startAtWord(wordIndex);
      },
      listenFromHere,
      stop: () => stop(),
      isActive: () => phaseRef.current !== "idle",
    }),
    [listenFromHere, startAtWord, stop, togglePlay],
  );

  return (
    <>
    <div className="flex flex-wrap items-center gap-2">
      {phase === "idle" ? (
        <Button
          size="sm"
          variant="outline"
          title="Listen from the beginning (L)"
          onClick={() => {
            void startAtWord(0);
          }}
        >
          <Volume2 className="size-3.5" />
          {noteMode ? "Listen on this note" : "Listen"}
        </Button>
      ) : null}
      {phase === "loading" ? (
        <Button size="sm" variant="outline" disabled>
          <LoaderCircle className="size-3.5 animate-spin" />
          Preparing speech…
        </Button>
      ) : null}
      {phase === "playing" ? (
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            audioRef.current?.pause();
            stopCueLoop();
            persistCue();
            setPhase("paused");
          }}
        >
          <Pause className="size-3.5" />
          Pause
        </Button>
      ) : null}
      {phase === "paused" ? (
        <Button
          size="sm"
          variant="outline"
          onClick={() => {
            const audio = audioRef.current;
            if (audio) applyPlaybackRate(audio, speedRef.current);
            void audio?.play().then(() => {
              startCueLoop();
              setPhase("playing");
            });
          }}
        >
          <Volume2 className="size-3.5" />
          Resume
        </Button>
      ) : null}
      {phase !== "idle" && phase !== "loading" ? (
        <Button size="sm" variant="ghost" onClick={() => stop()}>
          <Square className="size-3" />
          Stop
        </Button>
      ) : null}
      {noteMode ? null : (
      <Button size="sm" variant="ghost" title="Listen from the selected word (Shift+L)" onClick={listenFromHere}>
        Listen from here
      </Button>
      )}
      <label className="sr-only" htmlFor={`voice-${articleId}`}>
        Voice
      </label>
      <select
        id={`voice-${articleId}`}
        className={cn("h-7 rounded-md border border-border bg-background px-2 text-[0.8rem]", phase !== "idle" && "opacity-70")}
        value={voiceId}
        disabled={phase === "loading"}
        onChange={(event) => {
          const next = event.target.value;
          setVoiceId(next);
          if (phase !== "idle") void playChunk(0, next, null);
        }}
      >
        {(status?.voices.length ? status.voices : [{ voice_id: "eve", name: "Eve" }]).map((voice: { voice_id: string; name: string }) => (
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
    <Dialog open={planOpen} onOpenChange={setPlanOpen}>
      <DialogContent>
        <DialogHeader>
          <DialogTitle>This note is long to speak</DialogTitle>
          <DialogDescription>
            About {plan ? plan.chars.toLocaleString() : ""} characters. Confirm a full listen, or speak one chapter. Audio is
            cached until this listen ends or 24 hours pass.
          </DialogDescription>
        </DialogHeader>
        {plan && plan.sections.length > 1 ? (
          <div className="max-h-40 space-y-1 overflow-y-auto">
            {plan.sections.map((section) => (
              <Button
                key={section.id}
                type="button"
                size="sm"
                variant="outline"
                className="w-full justify-start"
                onClick={() => {
                  setPlanOpen(false);
                  void startAtWord(0, { section: section.id });
                }}
              >
                {section.title}
                <span className="ml-auto text-[11px] text-muted-foreground">{section.chars.toLocaleString()} chars</span>
              </Button>
            ))}
          </div>
        ) : null}
        <DialogFooter>
          <Button type="button" variant="outline" onClick={() => setPlanOpen(false)}>
            Cancel
          </Button>
          <Button
            type="button"
            onClick={() => {
              setPlanOpen(false);
              void startAtWord(pendingWordRef.current, { confirm: true, section: null });
            }}
          >
            Listen to all
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
});
