"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { api, ApiError } from "@/lib/api";
import {
  buildFunctionCallOutput,
  buildRealtimeUrl,
  buildResponseCreate,
  buildSessionUpdate,
  classifyRealtimeEvent,
  encodeMicChunk,
  extractAudioDelta,
  extractConversationId,
  extractFunctionCall,
  extractUserTranscript,
  extractTranscriptItemId,
  MAX_RECONNECT_ATTEMPTS,
  MIC_PROCESSOR_BUFFER,
  nextBackoffDelay,
  REALTIME_SAMPLE_RATE,
  runJuniorTool,
  splitMicChunks,
  type JuniorFunctionCall,
} from "@/lib/conversation-voice";
import { base64ToUint8Array, pcm16ToFloat32 } from "@/lib/use-realtime-voice";
import { micDeniedMessage } from "@/lib/stt-ui";

export type ConversationStatus = "idle" | "connecting" | "listening" | "speaking" | "thinking";

export interface UseConversationVoiceOptions {
  /** Live voice id — read through a ref so voice changes never reopen the socket. */
  voiceIdRef: React.RefObject<string>;
  /** Called with the user's transcribed speech so the pane can send it as a message. */
  onUserTranscript: (text: string) => void;
  /** Called whenever the mic/speaker status changes, for pane chrome. */
  onStatusChange?: (status: ConversationStatus) => void;
}

/** Conversation-mode chrome. Keep copy identical in the button title and status line. */
export const CONVERSATION_STATUS_LABEL: Record<ConversationStatus, string> = {
  idle: "",
  connecting: "Talk — connecting…",
  listening: "Talk — listening…",
  speaking: "Talk — Junior is speaking…",
  thinking: "Talk — checking your library…",
};

/**
 * Owns the xAI Realtime speech-to-speech loop for the Junior pane:
 * mic PCM16 in over one WebSocket, assistant PCM16 out, server VAD,
 * barge-in on speech_started, session resumption, token re-mint + backoff.
 */
export function useConversationVoice({
  voiceIdRef,
  onUserTranscript,
  onStatusChange,
}: UseConversationVoiceOptions) {
  const [status, setStatus] = useState<ConversationStatus>("idle");

  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const micStreamRef = useRef<MediaStream | null>(null);
  const micSourceRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const micProcessorRef = useRef<ScriptProcessorNode | null>(null);
  const sourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const nextStartTimeRef = useRef(0);
  const conversationIdRef = useRef<string | null>(null);
  const reconnectAttemptRef = useRef(0);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const manualStopRef = useRef(false);
  const startingRef = useRef(false);
  /**
   * Monotonic session generation. Every start() invocation captures its own
   * generation and re-checks it after each await; stop() and any newer start()
   * bump the counter, so a superseded start bails instead of building a second
   * socket/mic/context alongside the live one. A single shared boolean cannot
   * distinguish two in-flight starts — that race leaked a duplicate mic and
   * cross-fed the new socket with the stale one.
   */
  const sessionRef = useRef(0);
  const statusRef = useRef<ConversationStatus>("idle");
  const onUserTranscriptRef = useRef(onUserTranscript);
  const onStatusChangeRef = useRef(onStatusChange);
  /**
   * Completed function-call ids already handled. xAI emits the completed call
   * twice — response.function_call_arguments.done AND inside
   * response.output_item.done — so the dedupe set keeps each call to exactly
   * one handler run (and one output sent back per call_id).
   */
  const handledToolCallsRef = useRef<Set<string>>(new Set());
  // Per-session set of transcription item_ids already recorded — xAI repeats
  // transcription.completed three times per utterance; cleared in stop() so it
  // stays bounded across Talk sessions (same lifecycle as handledToolCallsRef).
  const handledTranscriptItemsRef = useRef<Set<string>>(new Set());

  useEffect(() => {
    onUserTranscriptRef.current = onUserTranscript;
    onStatusChangeRef.current = onStatusChange;
  }, [onUserTranscript, onStatusChange]);

  const setStatusSafe = useCallback((next: ConversationStatus) => {
    if (statusRef.current === next) return;
    statusRef.current = next;
    setStatus(next);
    onStatusChangeRef.current?.(next);
  }, []);

  // start is referenced by the reconnect timer; the live ref breaks the cycle.
  const startRef = useRef<(resume: boolean) => Promise<void>>(async () => {});

  /** Barge-in: kill every scheduled assistant buffer so the mic is heard instantly. */
  const stopPlayback = useCallback(() => {
    for (const source of sourcesRef.current) {
      try {
        source.onended = null;
        source.stop();
        source.disconnect();
      } catch {
        /* already stopped */
      }
    }
    sourcesRef.current.clear();
    const ctx = audioCtxRef.current;
    nextStartTimeRef.current = ctx ? ctx.currentTime + 0.05 : 0;
  }, []);

  /** Tear down transport only — keeps conversationIdRef for resumption. */
  const teardownTransport = useCallback(() => {
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws) {
      ws.onopen = null;
      ws.onmessage = null;
      ws.onclose = null;
      ws.onerror = null;
      try {
        ws.close();
      } catch {
        /* ignore */
      }
    }
    stopPlayback();
    const processor = micProcessorRef.current;
    micProcessorRef.current = null;
    if (processor) {
      processor.onaudioprocess = null;
      try {
        processor.disconnect();
      } catch {
        /* ignore */
      }
    }
    const micSource = micSourceRef.current;
    micSourceRef.current = null;
    if (micSource) {
      try {
        micSource.disconnect();
      } catch {
        /* ignore */
      }
    }
    const stream = micStreamRef.current;
    micStreamRef.current = null;
    if (stream) {
      for (const track of stream.getTracks()) {
        try {
          track.stop();
        } catch {
          /* ignore */
        }
      }
    }
  }, [stopPlayback]);

  const closeAudioContext = useCallback(() => {
    const ctx = audioCtxRef.current;
    audioCtxRef.current = null;
    if (ctx) {
      try {
        void ctx.close();
      } catch {
        /* ignore */
      }
    }
  }, []);

  const clearReconnectTimer = useCallback(() => {
    if (reconnectTimerRef.current != null) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
  }, []);

  const stop = useCallback(() => {
    // Invalidate every in-flight start() — a superseded start bails at its
    // next generation re-check without building a second session.
    sessionRef.current += 1;
    manualStopRef.current = true;
    startingRef.current = false;
    clearReconnectTimer();
    reconnectAttemptRef.current = 0;
    teardownTransport();
    closeAudioContext();
    conversationIdRef.current = null;
    // Tool-call dedupe state is per-session: clearing it here keeps the set
    // from growing unbounded across a long-lived pane with many Talk sessions.
    handledToolCallsRef.current.clear();
    handledTranscriptItemsRef.current.clear();
    setStatusSafe("idle");
  }, [clearReconnectTimer, closeAudioContext, setStatusSafe, teardownTransport]);

  const scheduleAssistantAudio = useCallback((delta: string) => {
    const ctx = audioCtxRef.current;
    if (!ctx || ctx.state === "closed") return;
    const pcm = base64ToUint8Array(delta);
    if (!pcm.length) return;
    const floats = pcm16ToFloat32(pcm);
    if (!floats.length) return;
    const buffer = ctx.createBuffer(1, floats.length, REALTIME_SAMPLE_RATE);
    buffer.getChannelData(0).set(floats);
    const source = ctx.createBufferSource();
    source.buffer = buffer;
    source.connect(ctx.destination);
    const startTime = Math.max(ctx.currentTime + 0.05, nextStartTimeRef.current);
    try {
      source.start(startTime);
    } catch {
      return;
    }
    nextStartTimeRef.current = startTime + buffer.duration;
    sourcesRef.current.add(source);
    source.onended = () => {
      sourcesRef.current.delete(source);
      try {
        source.disconnect();
      } catch {
        /* ignore */
      }
    };
    setStatusSafe("speaking");
  }, [setStatusSafe]);

  /**
   * Junior's function-call loop: run the tool, return its output to xAI, and
   * ask for the spoken answer. Verified live against xAI realtime — the
   * conversation.item.create (function_call_output) + response.create pair
   * makes Junior speak the tool result.
   */
  const handleJuniorToolCall = useCallback(
    async (socket: WebSocket, session: number, call: JuniorFunctionCall) => {
      // xAI emits the completed call twice (arguments.done and again inside
      // output_item.done) — the dedupe set keeps one handler run per call.
      if (handledToolCallsRef.current.has(call.call_id)) return;
      handledToolCallsRef.current.add(call.call_id);
      // A stop() or a newer start() owns the session now — bail.
      if (session !== sessionRef.current) return;
      console.log("junior-talk", { action: "tool-call", name: call.name });
      setStatusSafe("thinking");
      const result = await runJuniorTool(call.name, call.arguments);
      console.log("junior-talk", { action: "tool-result", name: call.name, chars: result.length });
      // Stale guards: a torn-down session or a closed socket must never get
      // the late result — barge-in and reconnects rely on this.
      if (session !== sessionRef.current) return;
      if (socket.readyState !== WebSocket.OPEN) return;
      try {
        socket.send(JSON.stringify(buildFunctionCallOutput(call.call_id, result)));
        socket.send(JSON.stringify(buildResponseCreate()));
      } catch {
        /* socket closed mid-send; the close handler reconnects */
      }
    },
    [setStatusSafe],
  );

  const scheduleReconnect = useCallback(() => {
    if (manualStopRef.current) return;
    if (reconnectAttemptRef.current >= MAX_RECONNECT_ATTEMPTS) {
      setStatusSafe("idle");
      return;
    }
    // Use the unit-tested helper so the MAX_BACKOFF_MS clamp is real in production.
    const delay = nextBackoffDelay(reconnectAttemptRef.current);
    reconnectAttemptRef.current += 1;
    clearReconnectTimer();
    reconnectTimerRef.current = setTimeout(() => {
      reconnectTimerRef.current = null;
      void startRef.current(true);
    }, delay);
  }, [clearReconnectTimer, setStatusSafe]);

  const start = useCallback(
    async (resume = false) => {
      const active = statusRef.current !== "idle";
      if (active) return;
      // A user-initiated stop cancels the CURRENT session only — re-arm so the
      // Talk button works again after "End conversation mode".
      manualStopRef.current = false;
      // This start supersedes any earlier in-flight start (rapid Talk taps):
      // the generation is re-checked after every await, so a stale start bails
      // without building a second socket/mic/context alongside the live one.
      const session = ++sessionRef.current;
      startingRef.current = true;
      setStatusSafe("connecting");
      console.log("junior-talk", { action: resume ? "resume" : "start" });

      let token: string;
      try {
        const tokenData = await api.realtimeToken();
        token = tokenData.value;
        if (!token) throw new Error("Realtime token is empty.");
      } catch (error) {
        // A newer start() or a stop() owns the session now — bail without
        // touching shared state (startingRef/status belong to the newer one).
        if (session !== sessionRef.current) return;
        startingRef.current = false;
        setStatusSafe("idle");
        // A 4xx from the token mint is a permanent auth failure — retrying a socket
        // that was never opened just burns all 5 reconnect attempts.
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) {
          console.log("junior-talk", { action: "token-fail", status: error.status });
          return;
        }
        scheduleReconnect();
        return;
      }
      // A newer start() or a stop() superseded this one while the token was in
      // flight — bail before building anything.
      if (session !== sessionRef.current) return;

      let audioCtx: AudioContext | null = null;
      try {
        audioCtx = new AudioContext({ sampleRate: REALTIME_SAMPLE_RATE });
        // Assign before resume() so the failure path below can close it —
        // otherwise a throwing resume() leaks the context forever.
        audioCtxRef.current = audioCtx;
        await audioCtx.resume();
        if (audioCtx.state !== "running") {
          throw new Error("AudioContext failed to start.");
        }
      } catch {
        if (session !== sessionRef.current) {
          // Superseded mid-resume: close the context only if it is still ours.
          if (audioCtx && audioCtxRef.current === audioCtx) closeAudioContext();
          return;
        }
        startingRef.current = false;
        closeAudioContext();
        setStatusSafe("idle");
        scheduleReconnect();
        return;
      }
      // A stop() or a newer start() landed while the context was resuming.
      if (session !== sessionRef.current) {
        if (audioCtxRef.current === audioCtx) closeAudioContext();
        return;
      }
      nextStartTimeRef.current = audioCtx.currentTime + 0.05;

      let stream: MediaStream;
      try {
        stream = await navigator.mediaDevices.getUserMedia({
          audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
        });
      } catch (error) {
        if (session !== sessionRef.current) {
          if (audioCtxRef.current === audioCtx) closeAudioContext();
          return;
        }
        startingRef.current = false;
        closeAudioContext();
        setStatusSafe("idle");
        console.log("junior-talk", { action: "mic-fail", message: micDeniedMessage(error) });
        return;
      }
      // The user may have tapped stop (or started a new session) while the mic
      // was being granted — tear down everything this start created.
      if (session !== sessionRef.current) {
        if (audioCtxRef.current === audioCtx) closeAudioContext();
        for (const track of stream.getTracks()) {
          try {
            track.stop();
          } catch {
            /* ignore */
          }
        }
        return;
      }
      micStreamRef.current = stream;

      const ws = new WebSocket(
        buildRealtimeUrl(resume ? conversationIdRef.current : null),
        `xai-client-secret.${token}`,
      );
      wsRef.current = ws;

      ws.onopen = () => {
        if (wsRef.current !== ws) return;
        reconnectAttemptRef.current = 0;
        ws.send(
          JSON.stringify(
            buildSessionUpdate(voiceIdRef.current || "castor", resume ? conversationIdRef.current : null),
          ),
        );
      };

      ws.onmessage = (event: MessageEvent) => {
        if (wsRef.current !== ws) return;
        let msg: Record<string, unknown>;
        try {
          msg = JSON.parse(event.data as string);
        } catch {
          return;
        }
        const kind = classifyRealtimeEvent(msg.type);
        // Junior's function tools: the completed call arrives as
        // response.function_call_arguments.done (and again inside
        // response.output_item.done — handled once via the dedupe set).
        // Tool turns stay inside the realtime session; only the user's
        // transcribed speech goes to the chat record below, untouched.
        const toolCall = extractFunctionCall(msg);
        if (toolCall) {
          void handleJuniorToolCall(ws, session, toolCall);
          return;
        }
        switch (kind) {
          case "conversation": {
            const id = extractConversationId(msg);
            if (id) conversationIdRef.current = id;
            break;
          }
          case "speech-start":
            // Barge-in: the user is talking, so the assistant goes silent now.
            stopPlayback();
            setStatusSafe("listening");
            break;
          case "user-transcript": {
            const text = extractUserTranscript(msg);
            if (text) {
              // xAI repeats transcription.completed three times per utterance
              // (same item_id, distinct event_ids). Dedupe on item_id so one
              // spoken turn yields exactly one transcript record; without this
              // every turn was sent to the chat 3× — Junior answering the same
              // thing repeatedly and the message list flickering per duplicate.
              const itemId = extractTranscriptItemId(msg);
              if (itemId) {
                if (handledTranscriptItemsRef.current.has(itemId)) break;
                handledTranscriptItemsRef.current.add(itemId);
              }
              console.log("junior-talk", { action: "user-transcript", chars: text.length });
              onUserTranscriptRef.current(text);
            }
            break;
          }
          case "assistant-audio": {
            const delta = extractAudioDelta(msg);
            if (delta) scheduleAssistantAudio(delta);
            break;
          }
          case "assistant-done":
            setStatusSafe("listening");
            break;
          case "error": {
            const message =
              typeof (msg as { error?: { message?: unknown } }).error?.message === "string"
                ? (msg as { error: { message: string } }).error.message
                : "Conversation error";
            console.log("junior-talk", { action: "error", message });
            break;
          }
          default:
            break;
        }
      };

      ws.onclose = () => {
        if (wsRef.current !== ws) return;
        wsRef.current = null;
        // Tear the whole transport down BEFORE reconnecting: stop the mic tracks,
        // disconnect the processor, close the AudioContext. Skipping this leaked a
        // live mic + context per reconnect, and the orphaned processor kept
        // appending audio to the NEW socket via the shared wsRef.
        teardownTransport();
        closeAudioContext();
        if (manualStopRef.current) return;
        setStatusSafe("idle");
        scheduleReconnect();
      };

      ws.onerror = () => {
        if (wsRef.current !== ws) return;
        console.log("junior-talk", { action: "ws-error" });
      };

      // Mic -> ScriptProcessor -> PCM16 base64 -> input_audio_buffer.append.
      // server_vad commits each turn server-side, so we never send commit here.
      const micSource = audioCtx.createMediaStreamSource(stream);
      const processor = audioCtx.createScriptProcessor(MIC_PROCESSOR_BUFFER, 1, 1);
      micSourceRef.current = micSource;
      micProcessorRef.current = processor;
      processor.onaudioprocess = (event: AudioProcessingEvent) => {
        const socket = wsRef.current;
        if (!socket || socket.readyState !== WebSocket.OPEN) return;
        const input = event.inputBuffer.getChannelData(0);
        // Split the ~170ms ScriptProcessor buffer into ~100ms appends (the
        // documented chunk size server_vad expects).
        for (const chunk of splitMicChunks(input)) {
          const encoded = encodeMicChunk(chunk);
          try {
            socket.send(JSON.stringify({ type: "input_audio_buffer.append", audio: encoded }));
          } catch {
            /* socket closed mid-send; the close handler reconnects */
            return;
          }
        }
      };
      micSource.connect(processor);
      // Route through a zero-gain sink so the processor runs without echoing the mic.
      const sink = audioCtx.createGain();
      sink.gain.value = 0;
      processor.connect(sink);
      sink.connect(audioCtx.destination);

      startingRef.current = false;
      setStatusSafe("listening");
    },
    [closeAudioContext, handleJuniorToolCall, scheduleAssistantAudio, scheduleReconnect, setStatusSafe, stopPlayback, teardownTransport, voiceIdRef],
  );

  useEffect(() => {
    startRef.current = start;
  }, [start]);

  useEffect(() => {
    return () => {
      sessionRef.current += 1;
      manualStopRef.current = true;
      clearReconnectTimer();
      teardownTransport();
      closeAudioContext();
    };
  }, [clearReconnectTimer, closeAudioContext, teardownTransport]);

  // Stable identity so pane effects keyed on `conversation` don't re-run every render.
  return useMemo(() => ({ status, start, stop }), [status, start, stop]);
}
