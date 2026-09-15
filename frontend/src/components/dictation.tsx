"use client";

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { Mic } from "lucide-react";
import { toast } from "sonner";
import { appendSpoken, newFinalSegment, normalizeSpoken } from "@/lib/stt-buffer";
import {
  MIC_DENIED_TOAST,
  MIC_DROPPED_TOAST,
  MIC_IDLE,
  MIC_LIVE,
} from "@/lib/stt-ui";
import { cn } from "@/lib/utils";

type Field = HTMLInputElement | HTMLTextAreaElement;

type StartOptions = {
  /** When true, keep the session open across utterances until Stop. */
  continuous?: boolean;
  /** Reconnect after idle/drop without wiping committed finals. */
  resume?: boolean;
};

export type DictationSink = {
  getValue: () => string;
  append: (piece: string) => void;
};

type DictationApi = {
  listening: boolean;
  sessionContinuous: boolean;
  continuous: boolean;
  idleHint: string | null;
  setContinuous: (value: boolean) => void;
  startFor: (field: Field, options?: StartOptions) => void;
  stop: () => void;
  abort: () => void;
  attach: (field: Field | null) => void;
  setSink: (sink: DictationSink | null) => void;
};

function sttToast(message: string) {
  const text = message.trim();
  toast.error(text || "STT failed");
}

function micDeniedMessage(error: unknown) {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError") {
      return MIC_DENIED_TOAST;
    }
    if (error.name === "NotFoundError") {
      return "No microphone found.";
    }
  }
  return error instanceof Error ? error.message : "Microphone is not available";
}

const DictationContext = createContext<DictationApi | null>(null);

function nativeSetValue(el: Field, value: string) {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const desc = Object.getOwnPropertyDescriptor(proto, "value");
  desc?.set?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

function insertFinal(el: Field, spoken: string) {
  const next = appendSpoken(el.value, spoken);
  if (next === el.value) return;
  nativeSetValue(el, next);
  const at = next.length;
  requestAnimationFrame(() => {
    el.focus();
    el.setSelectionRange(at, at);
  });
}

function downsample(input: Float32Array, fromRate: number, toRate: number) {
  if (fromRate === toRate) return input;
  const ratio = fromRate / toRate;
  const length = Math.max(1, Math.round(input.length / ratio));
  const out = new Float32Array(length);
  for (let i = 0; i < length; i += 1) {
    out[i] = input[Math.min(input.length - 1, Math.floor(i * ratio))] || 0;
  }
  return out;
}

function floatToPcm16(input: Float32Array) {
  const buffer = new ArrayBuffer(input.length * 2);
  const view = new DataView(buffer);
  for (let i = 0; i < input.length; i += 1) {
    const sample = Math.max(-1, Math.min(1, input[i] || 0));
    view.setInt16(i * 2, sample < 0 ? sample * 0x8000 : sample * 0x7fff, true);
  }
  return buffer;
}

export function DictationProvider({ children }: { children: ReactNode }) {
  const [listening, setListening] = useState(false);
  const [continuous, setContinuous] = useState(false);
  const [sessionContinuousMode, setSessionContinuousMode] = useState(false);
  const [interim, setInterim] = useState("");
  const [idleHint, setIdleHint] = useState<string | null>(null);
  const fieldRef = useRef<Field | null>(null);
  const sinkRef = useRef<DictationSink | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<{
    stream: MediaStream;
    context: AudioContext;
    processor: ScriptProcessorNode;
  } | null>(null);
  const committedRef = useRef("");
  const interimRef = useRef("");
  const lastRawFinalRef = useRef("");
  const listeningRef = useRef(false);
  const continuousRef = useRef(false);
  const sessionContinuousRef = useRef(false);
  const stoppingRef = useRef(false);
  const abortedRef = useRef(false);
  const startingRef = useRef(false);
  const closedCleanlyRef = useRef(false);
  const deniedToastRef = useRef(false);
  const startForRef = useRef<(field: Field, options?: StartOptions) => void>(() => {});
  useEffect(() => {
    continuousRef.current = continuous;
    listeningRef.current = listening;
  }, [continuous, listening]);

  const disconnectEngine = useCallback((opts?: { keepUi?: boolean }) => {
    closedCleanlyRef.current = true;
    startingRef.current = false;
    if (!opts?.keepUi) {
      listeningRef.current = false;
      setListening(false);
    }
    interimRef.current = "";
    setInterim("");
    const audio = audioRef.current;
    audioRef.current = null;
    if (audio) {
      try {
        audio.processor.disconnect();
      } catch {
        /* ignore */
      }
      audio.stream.getTracks().forEach((track) => track.stop());
      void audio.context.close();
    }
    const socket = socketRef.current;
    socketRef.current = null;
    if (socket) {
      try {
        if (socket.readyState === WebSocket.OPEN) {
          socket.send(JSON.stringify({ type: "stop" }));
        }
      } catch {
        /* ignore */
      }
      try {
        socket.close();
      } catch {
        /* ignore */
      }
    }
  }, []);

  const teardown = useCallback(() => {
    stoppingRef.current = false;
    disconnectEngine();
    setSessionContinuousMode(false);
    sessionContinuousRef.current = false;
    committedRef.current = "";
    lastRawFinalRef.current = "";
  }, [disconnectEngine]);

  const sleepMic = useCallback(
    (hint: string, toastDropped = false) => {
      stoppingRef.current = false;
      abortedRef.current = false;
      disconnectEngine();
      setIdleHint(hint);
      if (toastDropped) sttToast(hint);
    },
    [disconnectEngine],
  );

  const commitFinal = useCallback((raw: string) => {
    if (abortedRef.current) return;
    const spoken = normalizeSpoken(raw);
    if (!spoken) return;
    if (spoken === lastRawFinalRef.current) return;
    const el = fieldRef.current;
    const fieldValue = sinkRef.current?.getValue() ?? el?.value ?? "";
    const piece = newFinalSegment(raw, committedRef.current, fieldValue);
    interimRef.current = "";
    setInterim("");
    if (!piece) {
      lastRawFinalRef.current = spoken;
      return;
    }
    lastRawFinalRef.current = spoken;
    if (sinkRef.current) sinkRef.current.append(piece);
    else if (el) insertFinal(el, piece);
    committedRef.current = normalizeSpoken(`${committedRef.current} ${piece}`);
  }, []);

  /** Drop the mic immediately. Must never delay /chat (no wait for STT done). */
  const abort = useCallback(() => {
    abortedRef.current = true;
    stoppingRef.current = true;
    setIdleHint(null);
    teardown();
  }, [teardown]);

  const startFor = useCallback(
    (field: Field, options?: StartOptions) => {
      const live = socketRef.current;
      const resuming = Boolean(options?.resume);
      const busy =
        listeningRef.current ||
        startingRef.current ||
        (live != null && live.readyState <= WebSocket.OPEN);
      if (!resuming && busy) {
        abort();
        if (fieldRef.current === field && !resuming) return;
      }
      if (resuming) {
        disconnectEngine({ keepUi: true });
      }
      abortedRef.current = false;
      setIdleHint(null);
      fieldRef.current = field;
      field.focus();
      startingRef.current = true;
      stoppingRef.current = false;
      const sessionContinuous = options?.continuous ?? continuousRef.current;
      sessionContinuousRef.current = sessionContinuous;
      setSessionContinuousMode(sessionContinuous);
      if (!resuming) {
        committedRef.current = "";
        lastRawFinalRef.current = "";
        interimRef.current = "";
        setInterim("");
      }
      void (async () => {
        let context: AudioContext | null = null;
        try {
          const AudioCtx =
            window.AudioContext ||
            (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
          if (!AudioCtx) throw new Error("Microphone is not available");
          context = new AudioCtx();
          if (context.state === "suspended") await context.resume();
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
          deniedToastRef.current = false;
          if (!startingRef.current || abortedRef.current) {
            stream.getTracks().forEach((track) => track.stop());
            void context.close();
            return;
          }
          const protocol = window.location.protocol === "https:" ? "wss" : "ws";
          const params = new URLSearchParams();
          if (sessionContinuous) params.set("continuous", "true");
          const socket = new WebSocket(`${protocol}://${window.location.host}/api/v1/stt?${params.toString()}`);
          socket.binaryType = "arraybuffer";
          socketRef.current = socket;
          const pending: ArrayBuffer[] = [];
          const flushPending = () => {
            while (pending.length && socket.readyState === WebSocket.OPEN) {
              socket.send(pending.shift()!);
            }
          };
          socket.onmessage = (event) => {
            try {
              const msg = JSON.parse(String(event.data)) as {
                type?: string;
                text?: string;
                is_final?: boolean;
                speech_final?: boolean;
                message?: string;
              };
              if (msg.type === "ready") {
                listeningRef.current = true;
                startingRef.current = false;
                setListening(true);
                flushPending();
                return;
              }
              if (msg.type === "partial") {
                const text = msg.text || "";
                if (msg.is_final || msg.speech_final) {
                  commitFinal(text);
                  return;
                }
                interimRef.current = text;
                setInterim(text);
                return;
              }
              if (msg.type === "done") {
                if (msg.text) commitFinal(msg.text);
                lastRawFinalRef.current = "";
                if (!sessionContinuousRef.current) {
                  teardown();
                }
                return;
              }
              if (msg.type === "error") {
                sttToast(msg.message || "STT failed");
                teardown();
                return;
              }
              if (msg.type === "timeout") {
                if (sessionContinuousRef.current) {
                  sleepMic(msg.message || MIC_IDLE);
                  return;
                }
                sttToast(msg.message || "STT timeout");
                teardown();
                return;
              }
              if (msg.type === "idle") {
                sleepMic(msg.message || MIC_IDLE);
              }
            } catch {
              /* ignore */
            }
          };
          socket.onerror = () => {
            /* onclose sets idle / dropped; avoid a second toast */
          };
          socket.onclose = (event) => {
            if (closedCleanlyRef.current) {
              closedCleanlyRef.current = false;
              return;
            }
            const fatal =
              event.code === 4403 || event.code === 4503 || event.code === 4409 || event.code === 4429;
            if (event.code === 4403) sttToast("Demo account — dictation is off");
            else if (event.code === 4503) sttToast("STT is off until XAI_API_KEY is set on the server");
            else if (event.code === 4409) sttToast("Dictation is already open in another tab");
            else if (event.code === 4429) sttToast("STT rate limit reached");
            if (fatal) {
              stoppingRef.current = true;
              teardown();
              return;
            }
            if (stoppingRef.current || abortedRef.current) return;
            if (sessionContinuousRef.current) {
              sleepMic(MIC_DROPPED_TOAST, true);
              return;
            }
            if (!listeningRef.current && !startingRef.current) return;
            teardown();
          };
          await new Promise<void>((resolve, reject) => {
            socket.onopen = () => resolve();
            socket.addEventListener("error", () => reject(new Error("socket")), { once: true });
          });
          if (!startingRef.current && !listeningRef.current) {
            stream.getTracks().forEach((track) => track.stop());
            void context.close();
            return;
          }
          if (context.state === "suspended") await context.resume();
          const source = context.createMediaStreamSource(stream);
          const processor = context.createScriptProcessor(4096, 1, 1);
          processor.onaudioprocess = (event) => {
            if (socket.readyState !== WebSocket.OPEN || stoppingRef.current || abortedRef.current) return;
            const pcm = floatToPcm16(downsample(event.inputBuffer.getChannelData(0), context!.sampleRate, 16000));
            if (!listeningRef.current) {
              pending.push(pcm);
              if (pending.length > 24) pending.shift();
              return;
            }
            socket.send(pcm);
          };
          const mute = context.createGain();
          mute.gain.value = 0;
          source.connect(processor);
          processor.connect(mute);
          mute.connect(context.destination);
          audioRef.current = { stream, context, processor };
          context = null;
        } catch (error) {
          const denied =
            error instanceof DOMException &&
            (error.name === "NotAllowedError" || error.name === "PermissionDeniedError");
          if (denied) {
            if (!deniedToastRef.current) {
              deniedToastRef.current = true;
              sttToast(MIC_DENIED_TOAST);
            }
          } else {
            sttToast(micDeniedMessage(error));
          }
          if (context) void context.close();
          teardown();
        }
      })();
    },
    [abort, commitFinal, disconnectEngine, sleepMic, teardown],
  );
  startForRef.current = startFor;

  const setContinuousMode = useCallback((value: boolean) => {
    setContinuous(value);
    continuousRef.current = value;
    if (listeningRef.current || startingRef.current) {
      sessionContinuousRef.current = value;
      setSessionContinuousMode(value);
      const el = fieldRef.current;
      if (el && value) {
        startForRef.current(el, { continuous: true, resume: true });
      }
    }
  }, []);

  const attach = useCallback((field: Field | null) => {
    if (!field) return;
    const current = fieldRef.current;
    if ((listeningRef.current || startingRef.current) && current && current !== field && document.contains(current)) {
      return;
    }
    fieldRef.current = field;
  }, []);

  const setSink = useCallback((sink: DictationSink | null) => {
    sinkRef.current = sink;
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape" || (!listeningRef.current && !startingRef.current && !idleHint)) return;
      if (!listeningRef.current && !startingRef.current) return;
      event.preventDefault();
      event.stopPropagation();
      abort();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [abort, idleHint]);

  useEffect(() => {
    function onGone() {
      if (listeningRef.current || startingRef.current) abort();
    }
    window.addEventListener("pagehide", onGone);
    window.addEventListener("popstate", onGone);
    return () => {
      window.removeEventListener("pagehide", onGone);
      window.removeEventListener("popstate", onGone);
      teardown();
    };
  }, [abort, teardown]);

  const api: DictationApi = {
    listening,
    sessionContinuous: sessionContinuousMode,
    continuous,
    idleHint,
    setContinuous: setContinuousMode,
    startFor,
    stop: abort,
    abort,
    attach,
    setSink,
  };

  const live = listening;
  return (
    <DictationContext.Provider value={api}>
      {children}
      {live ? (
        <div className="pointer-events-auto fixed bottom-4 left-4 z-[80] flex max-w-[min(36rem,calc(100vw-2rem))] items-center gap-2 rounded-full border bg-background px-3 py-1.5 text-xs shadow-md">
          <span className="size-2 shrink-0 rounded-full bg-red-600" />
          <span className="font-medium shrink-0">{MIC_LIVE}</span>
          {interim ? (
            <span className="min-w-0 truncate text-muted-foreground" aria-live="polite">
              {interim}
            </span>
          ) : (
            <span className="text-muted-foreground">Waiting…</span>
          )}
          <label className="flex shrink-0 cursor-pointer items-center gap-1 text-muted-foreground">
            <input
              type="checkbox"
              checked={continuous}
              onChange={(event) => setContinuousMode(event.target.checked)}
              className="pointer-events-auto"
              aria-label="Continuous dictation"
            />
            Continuous
          </label>
          <button type="button" className="pointer-events-auto shrink-0 rounded-md border px-2 py-0.5" onClick={abort}>
            Stop
          </button>
        </div>
      ) : idleHint ? (
        <button
          type="button"
          className="pointer-events-auto fixed bottom-4 left-4 z-[80] max-w-[min(36rem,calc(100vw-2rem))] rounded-full border bg-background px-3 py-1.5 text-xs shadow-md"
          onClick={() => {
            const el = fieldRef.current;
            if (el) {
              startFor(el, {
                resume: true,
                continuous: continuousRef.current || sessionContinuousRef.current,
              });
            }
          }}
        >
          {idleHint.startsWith("Mic dropped") ? idleHint : `${MIC_IDLE} — tap to resume.`}
        </button>
      ) : null}
    </DictationContext.Provider>
  );
}

export function useDictation() {
  return useContext(DictationContext);
}

export function DictationMic({ target, className }: { target: () => Field | null; className?: string }) {
  const dictation = useDictation();
  if (!dictation) return null;
  return (
    <button
      type="button"
      className={cn(
        "absolute right-1 top-1/2 z-10 -translate-y-1/2 rounded-md p-1 text-muted-foreground hover:text-foreground",
        dictation.listening && "text-red-600",
        className,
      )}
      aria-label={dictation.listening ? "Stop dictation" : "Dictate"}
      onMouseDown={(event) => event.preventDefault()}
      onClick={() => {
        const el = target();
        if (el) dictation.startFor(el, { continuous: dictation.continuous });
      }}
    >
      <Mic className="size-3.5" />
    </button>
  );
}
