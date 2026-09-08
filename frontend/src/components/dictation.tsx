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
import { cn } from "@/lib/utils";

type Field = HTMLInputElement | HTMLTextAreaElement;

type DictationApi = {
  listening: boolean;
  continuous: boolean;
  setContinuous: (value: boolean) => void;
  startFor: (field: Field) => void;
  stop: () => void;
  attach: (field: Field | null) => void;
};

const DictationContext = createContext<DictationApi | null>(null);

function nativeSetValue(el: Field, value: string) {
  const proto = el instanceof HTMLTextAreaElement ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
  const desc = Object.getOwnPropertyDescriptor(proto, "value");
  desc?.set?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

function insertFinal(el: Field, spoken: string) {
  const text = spoken.trim();
  if (!text) return;
  const start = el.selectionStart ?? el.value.length;
  const end = el.selectionEnd ?? start;
  const before = el.value.slice(0, start);
  const after = el.value.slice(end);
  const padLeft = before && !/\s$/.test(before) ? " " : "";
  const next = `${before}${padLeft}${text}${after}`;
  nativeSetValue(el, next);
  const at = (before + padLeft + text).length;
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
  const fieldRef = useRef<Field | null>(null);
  const socketRef = useRef<WebSocket | null>(null);
  const audioRef = useRef<{
    stream: MediaStream;
    context: AudioContext;
    processor: ScriptProcessorNode;
  } | null>(null);
  const interimRef = useRef("");
  const baseRef = useRef("");
  const listeningRef = useRef(false);
  const continuousRef = useRef(false);
  continuousRef.current = continuous;
  listeningRef.current = listening;

  const teardown = useCallback(() => {
    listeningRef.current = false;
    setListening(false);
    interimRef.current = "";
    const audio = audioRef.current;
    audioRef.current = null;
    if (audio) {
      audio.processor.disconnect();
      audio.stream.getTracks().forEach((track) => track.stop());
      void audio.context.close();
    }
    const socket = socketRef.current;
    socketRef.current = null;
    if (socket && socket.readyState === WebSocket.OPEN) {
      socket.send(JSON.stringify({ type: "stop" }));
      socket.close();
    } else {
      socket?.close();
    }
  }, []);

  const applyPartial = useCallback((text: string, isFinal: boolean) => {
    const el = fieldRef.current;
    if (!el) return;
    if (isFinal) {
      nativeSetValue(el, baseRef.current);
      const at = baseRef.current.length;
      el.setSelectionRange(at, at);
      insertFinal(el, text);
      baseRef.current = el.value;
      interimRef.current = "";
      return;
    }
    if (!interimRef.current) baseRef.current = el.value;
    interimRef.current = text;
    const start = el.selectionStart ?? el.value.length;
    void start;
    nativeSetValue(el, `${baseRef.current}${baseRef.current && text ? " " : ""}${text}`);
  }, []);

  const startFor = useCallback(
    (field: Field) => {
      if (listeningRef.current && fieldRef.current === field) {
        teardown();
        return;
      }
      fieldRef.current = field;
      field.focus();
      void (async () => {
        teardown();
        try {
          const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
          const protocol = window.location.protocol === "https:" ? "wss" : "ws";
          const params = new URLSearchParams();
          if (continuousRef.current) params.set("continuous", "true");
          const socket = new WebSocket(`${protocol}://${window.location.host}/api/v1/stt?${params.toString()}`);
          socket.binaryType = "arraybuffer";
          socketRef.current = socket;
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
                setListening(true);
                return;
              }
              if (msg.type === "partial" && msg.text) {
                applyPartial(msg.text, Boolean(msg.is_final || msg.speech_final));
                return;
              }
              if (msg.type === "done" && msg.text) {
                applyPartial(msg.text, true);
                return;
              }
              if (msg.type === "error" || msg.type === "timeout" || msg.type === "idle") {
                if (msg.message) toast.error(msg.message);
                teardown();
              }
            } catch {
              /* ignore */
            }
          };
          socket.onerror = () => {
            toast.error("Dictation could not connect");
            teardown();
          };
          socket.onclose = () => {
            if (listeningRef.current) teardown();
          };
          await new Promise<void>((resolve, reject) => {
            socket.onopen = () => resolve();
            socket.addEventListener("error", () => reject(new Error("socket")), { once: true });
          });
          const context = new AudioContext();
          const source = context.createMediaStreamSource(stream);
          const processor = context.createScriptProcessor(4096, 1, 1);
          processor.onaudioprocess = (event) => {
            if (socket.readyState !== WebSocket.OPEN || !listeningRef.current) return;
            const pcm = floatToPcm16(downsample(event.inputBuffer.getChannelData(0), context.sampleRate, 16000));
            socket.send(pcm);
          };
          const mute = context.createGain();
          mute.gain.value = 0;
          source.connect(processor);
          processor.connect(mute);
          mute.connect(context.destination);
          audioRef.current = { stream, context, processor };
          baseRef.current = field.value;
        } catch (error) {
          toast.error(error instanceof Error ? error.message : "Microphone is not available");
          teardown();
        }
      })();
    },
    [applyPartial, teardown],
  );

  const attach = useCallback((field: Field | null) => {
    if (field) fieldRef.current = field;
  }, []);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (event.key !== "Escape" || !listeningRef.current) return;
      event.preventDefault();
      event.stopPropagation();
      teardown();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [teardown]);

  useEffect(() => {
    function onGone() {
      if (listeningRef.current) teardown();
    }
    window.addEventListener("pagehide", onGone);
    window.addEventListener("popstate", onGone);
    return () => {
      window.removeEventListener("pagehide", onGone);
      window.removeEventListener("popstate", onGone);
      teardown();
    };
  }, [teardown]);

  const api: DictationApi = {
    listening,
    continuous,
    setContinuous,
    startFor,
    stop: teardown,
    attach,
  };

  return (
    <DictationContext.Provider value={api}>
      {children}
      {listening ? (
        <div className="fixed bottom-4 left-4 z-[75] flex items-center gap-2 rounded-full border bg-background px-3 py-1.5 text-xs shadow-md">
          <span className="size-2 rounded-full bg-red-600" />
          <span className="font-medium">Listening</span>
          <label className="flex items-center gap-1 text-muted-foreground">
            <input
              type="checkbox"
              checked={continuous}
              onChange={(event) => setContinuous(event.target.checked)}
            />
            Continuous
          </label>
          <button type="button" className="rounded-md border px-2 py-0.5" onClick={teardown}>
            Stop
          </button>
        </div>
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
        if (el) dictation.startFor(el);
      }}
    >
      <Mic className="size-3.5" />
    </button>
  );
}
