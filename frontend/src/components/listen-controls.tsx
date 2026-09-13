"use client";

import { forwardRef, useCallback, useEffect, useImperativeHandle, useRef, useState } from "react";
import { LoaderCircle, Pause, Square, Volume2 } from "lucide-react";
import { toast } from "sonner";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogFooter, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { api } from "@/lib/api";
import { showTtsErrorToast } from "@/lib/tts-error-toast";
import { cueAheadOfVoice, timestampsMatchChunk, wordIndexAtTime } from "@/lib/tts-cue";
import {
  readStoredTtsSpeed,
  readStoredTtsVoice,
  TTS_SPEEDS,
  writeStoredTtsSpeed,
  writeStoredTtsVoice,
} from "@/lib/tts-preferences";
import { claimTtsPlayback, releaseTtsPlayback } from "@/lib/tts-session";
import { cn } from "@/lib/utils";
import type { TtsStatus, TtsWord } from "@/lib/types";

const FOLLOW_UNAVAILABLE = "Follow unavailable for this audio.";

type SpeechPayload = {
  blob: Blob;
  chunks: number;
  wordOffset: number;
  chunkWordCounts: number[];
  duration: number | null;
  words: TtsWord[];
  contentHash?: string;
  ttsWordCount?: number;
};

import type { VisibleSpeechPayload } from "@/lib/tts-visible";

const speechMemory = new Map<string, SpeechPayload>();

function memoryKey(articleId: string, voice: string, chunk: number, includeNotes: boolean, contentHash: string) {
  return `${articleId}:${contentHash || "pending"}:${voice}:${includeNotes ? "notes" : "body"}:${chunk}`;
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
    onFollowUnavailable?: () => void;
    getCaretWord?: () => number | null;
    getVisibleSpeech?: () => VisibleSpeechPayload | null;
    getVisibleSections?: () => import("@/lib/tts-visible").VisibleSpeechSection[];
  }
>(function ListenControls(
  {
    articleId,
    hasText,
    includeNotes = false,
    noteMode = false,
    onCue,
    onFollowUnavailable,
    getCaretWord,
    getVisibleSpeech,
    getVisibleSections,
  },
  ref,
) {
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
  const timestampsValidRef = useRef(false);
  const followToastShownRef = useRef(false);
  const confirmRef = useRef(false);
  const [planOpen, setPlanOpen] = useState(false);
  const [plan, setPlan] = useState<import("@/lib/types").TtsPlan | null>(null);
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
        const storedVoice = readStoredTtsVoice(next.voices[0]?.voice_id || "eve");
        const known = next.voices.some((voice) => voice.voice_id === storedVoice);
        if (known) setVoiceId(storedVoice);
        else if (next.voices[0]?.voice_id) setVoiceId(next.voices[0].voice_id);
      })
      .catch(() => {
        if (!cancelled) setStatus({ enabled: false, provider: "xai", voices: [] });
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    const next = readStoredTtsSpeed();
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

  const syncCueFromAudio = useCallback(() => {
    if (!timestampsValidRef.current) return;
    const audio = audioRef.current;
    const words = wordsRef.current;
    if (!audio || !words.length) return;
    const currentTime = audio.currentTime;
    const local = wordIndexAtTime(words, currentTime);
    if (local == null) return;
    if (cueAheadOfVoice(words, local, currentTime)) {
      const w = words[local];
      console.warn("[tts-cue]", {
        currentTime,
        wordStart: w?.start,
        wordEnd: w?.end,
        rate: audio.playbackRate,
      });
      return;
    }
    const next = wordOffsetRef.current + local;
    if (next !== lastCueRef.current) {
      lastCueRef.current = next;
      emitCue(next);
    }
  }, [emitCue]);

  const markTimestampsUnavailable = useCallback(() => {
    timestampsValidRef.current = false;
    stopCueLoop();
    lastCueRef.current = null;
    emitCue(null);
    if (!followToastShownRef.current) {
      followToastShownRef.current = true;
      toast(FOLLOW_UNAVAILABLE);
      onFollowUnavailable?.();
    }
  }, [emitCue, onFollowUnavailable, stopCueLoop]);

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

  const stop = useCallback(
    (clearResume = false) => {
      generationRef.current += 1;
      releaseTtsPlayback(stop);
      stopCueLoop();
      if (clearResume) {
        writeResume(articleId, null);
        void api.releaseTtsAudio(articleId, voiceRef.current).catch(() => undefined);
      }
      else persistCue();
      lastCueRef.current = null;
      emitCue(null);
      timestampsValidRef.current = false;
      followToastShownRef.current = false;
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
    timestampsValidRef.current = false;
    followToastShownRef.current = false;
    confirmRef.current = false;
    contentHashRef.current = "";
    const audio = new Audio();
    applyPlaybackRate(audio, speedRef.current);
    audioRef.current = audio;
    const onSeeked = () => syncCueFromAudio();
    audio.addEventListener("seeked", onSeeked);
    return () => {
      audio.removeEventListener("seeked", onSeeked);
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
  }, [articleId, includeNotes, onCue, persistCue, syncCueFromAudio]);

  const loadChunk = useCallback(
    async (index: number, voice: string) => {
      const key = memoryKey(articleId, voice, index, includeNotesRef.current, contentHashRef.current);
      const hit = speechMemory.get(key);
      if (hit) return hit;
      const visible = getVisibleSpeech?.();
      const data = visible?.script
        ? await api.articleSpeechVisible(
            articleId,
            voice,
            index,
            {
              visibleText: visible.script,
              includeNotes: false,
            },
            { confirm: confirmRef.current },
          )
        : await api.articleSpeech(articleId, voice, index, {
            confirm: confirmRef.current,
            includeNotes: includeNotesRef.current,
          });
      if (data.contentHash) contentHashRef.current = data.contentHash;
      if (visible && "ttsWordCount" in data && data.ttsWordCount) {
        const payload = {
          ttsWordCount: data.ttsWordCount,
          visibleWordCount: visible.visibleWordCount,
        };
        if (payload.ttsWordCount !== payload.visibleWordCount) {
          console.warn("[tts-visible] word count mismatch", payload);
        } else {
          console.info("[tts-visible]", payload);
        }
      }
      rememberSpeech(memoryKey(articleId, voice, index, includeNotesRef.current, contentHashRef.current), data);
      if (data.chunkWordCounts.length) countsRef.current = data.chunkWordCounts;
      return data;
    },
    [articleId, getVisibleSpeech, includeNotes],
  );

  const playChunk = useCallback(
    async (index: number, voice: string, seekLocal: number | null = null) => {
      claimTtsPlayback(() => stop());
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

      const seekAndPlay = async (
        words: TtsWord[],
        wordOffset: number,
        chunkIndex: number,
        chunkWordCounts: number[],
      ) => {
        wordsRef.current = words;
        wordOffsetRef.current = wordOffset;
        applyTimestampValidation(words, chunkIndex, chunkWordCounts);
        applyPlaybackRate(audio, speedRef.current);
        const applySeek = () => {
          if (seekLocal != null && seekLocal > 0) {
            if (timestampsValidRef.current && words[seekLocal]) {
              audio.currentTime = words[seekLocal].start;
            }
          } else if (seekLocal == null || seekLocal === 0) {
            audio.currentTime = 0;
          }
        };
        audio.onloadedmetadata = applySeek;
        applySeek();
        await audio.play();
        applySeek();
        applyPlaybackRate(audio, speedRef.current);
        if (generation !== generationRef.current) return;
        setPhase("playing");
        if (timestampsValidRef.current) {
          syncCueFromAudio();
          startCueLoop();
        }
      };

      const alreadyLoaded = loadedChunkRef.current === index && loadedVoiceRef.current === voice && Boolean(audio.src);
      if (alreadyLoaded && wordsRef.current.length) {
        const cached = speechMemory.get(
          memoryKey(articleId, voice, index, includeNotesRef.current, contentHashRef.current),
        );
        const total = cached?.chunks ?? 1;
        attachEnded(total);
        setChunk(index);
        setChunks(total);
        const counts = countsRef.current.length ? countsRef.current : cached?.chunkWordCounts || [];
        await seekAndPlay(wordsRef.current, wordOffsetRef.current, index, counts);
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
        const counts = data.chunkWordCounts.length ? data.chunkWordCounts : countsRef.current;
        await seekAndPlay(data.words, data.wordOffset, index, counts);
        if (index + 1 < data.chunks) {
          void loadChunk(index + 1, voice);
        }
      } catch (err) {
        if (generation !== generationRef.current) return;
        stop();
        showTtsErrorToast(err);
      }
    },
    [applyTimestampValidation, articleId, loadChunk, startCueLoop, stop, syncCueFromAudio],
  );

  const startAtWord = useCallback(
    async (wordIndex: number, opts?: { confirm?: boolean }) => {
      if (!hasText) {
        toast.error(noteMode ? "This note has no text to read." : "Extract the full text first, then listen.");
        return;
      }
      if (wordIndex > 0) {
        loadedChunkRef.current = null;
        loadedVoiceRef.current = null;
        countsRef.current = [];
        const audio = audioRef.current;
        if (audio) {
          audio.pause();
          audio.removeAttribute("src");
          audio.load();
        }
      }
      const voice = voiceRef.current;
      if (opts?.confirm) {
        confirmRef.current = true;
        countsRef.current = [];
        loadedChunkRef.current = null;
        loadedVoiceRef.current = null;
      }
      if (!noteMode) {
        getVisibleSpeech?.();
      }
      if (!confirmRef.current) {
        try {
          const visible = getVisibleSpeech?.();
          const nextPlan = visible?.script
            ? await api.ttsPlanVisible(articleId, {
                visibleText: visible.script,
                voiceId: voice,
                includeNotes: false,
              })
            : await api.ttsPlan(articleId, voice, { includeNotes: includeNotesRef.current });
          if (nextPlan.content_hash) contentHashRef.current = nextPlan.content_hash;
          if (visible) {
            const payload = {
              ttsWordCount: nextPlan.tts_word_count ?? 0,
              visibleWordCount: visible.visibleWordCount,
            };
            if (payload.ttsWordCount !== payload.visibleWordCount) {
              console.warn("[tts-visible] word count mismatch", payload);
            } else {
              console.info("[tts-visible]", payload);
            }
          }
          if (nextPlan.long) {
            pendingWordRef.current = wordIndex;
            const visibleSections = getVisibleSections?.() ?? [];
            const sections = visibleSections.length
              ? visibleSections.map((section) => ({
                  id: section.id,
                  title: section.title,
                  chars: 0,
                  word_offset: section.word_offset,
                }))
              : nextPlan.sections;
            setPlan({ ...nextPlan, sections });
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
    [articleId, getVisibleSections, getVisibleSpeech, hasText, includeNotes, loadChunk, noteMode, playChunk],
  );

  const listenFromHere = useCallback(() => {
    if (!hasText) {
      toast.error(noteMode ? "This note has no text to read." : "Extract the full text first, then listen.");
      return;
    }
    getVisibleSpeech?.();
    const word = getCaretWord?.();
    if (word == null || word < 0) {
      toast.error("Click or select a word in the article first.");
      return;
    }
    loadedChunkRef.current = null;
    loadedVoiceRef.current = null;
    countsRef.current = [];
    const audio = audioRef.current;
    if (audio) {
      audio.pause();
      audio.removeAttribute("src");
      audio.load();
    }
    void startAtWord(word);
  }, [getCaretWord, getVisibleSpeech, hasText, noteMode, startAtWord]);

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
            syncCueFromAudio();
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
          writeStoredTtsVoice(next);
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
          writeStoredTtsSpeed(next);
          const audio = audioRef.current;
          if (audio) applyPlaybackRate(audio, next);
        }}
      >
        {TTS_SPEEDS.map((rate) => (
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
            About {plan ? plan.chars.toLocaleString() : ""} characters. StoryKeep reads the full note in order. Confirm to
            start, or jump to a chapter heading and continue through the rest. Audio is cached until this listen ends or 24
            hours pass.
          </DialogDescription>
        </DialogHeader>
        {plan && plan.sections.length > 1 ? (
          <div className="max-h-40 space-y-1 overflow-y-auto">
            <p className="px-1 text-[11px] text-muted-foreground">Jump to chapter (reads through the end)</p>
            {plan.sections.map((section) => (
              <Button
                key={section.id}
                type="button"
                size="sm"
                variant="outline"
                className="w-full justify-start"
                onClick={() => {
                  setPlanOpen(false);
                  void startAtWord(section.word_offset ?? 0, { confirm: true });
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
              void startAtWord(pendingWordRef.current, { confirm: true });
            }}
          >
            {pendingWordRef.current > 0 ? "Listen from here" : "Listen to full note"}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
    </>
  );
});
