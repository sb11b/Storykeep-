"use client";

import { useCallback, useRef } from "react";
import type { RefObject } from "react";
import { showTtsErrorToast } from "@/lib/tts-error-toast";
import { readStoredTtsVoice } from "@/lib/tts-preferences";
import { DEFAULT_TTS_VOICE_ID } from "@/lib/tts-defaults";

/** Decode a base64 string into a Uint8Array. */
export function base64ToUint8Array(base64: string): Uint8Array {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes;
}

/** Convert interleaved PCM16 data to a Float32Array for Web Audio API. */
export function pcm16ToFloat32(pcm16: Uint8Array): Float32Array {
  const view = new DataView(pcm16.buffer, pcm16.byteOffset, pcm16.byteLength);
  const float32 = new Float32Array(view.byteLength / 2);
  for (let i = 0; i < float32.length; i++) {
    const int16 = view.getInt16(i * 2, true);
    float32[i] = int16 < 0 ? int16 / 0x8000 : int16 / 0x7fff;
  }
  return float32;
}

/** Owns the xAI Realtime voice session (WebSocket + AudioContext PCM16 streaming) extracted from grok-message-listen. */
export function useRealtimeVoice(
  voiceRef: RefObject<string>,
  stopRef: RefObject<() => void>,
) {
  const pcRef = useRef<RTCPeerConnection | null>(null);
  const dcRef = useRef<RTCDataChannel | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const audioCtxRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<AudioBufferSourceNode | null>(null);
  const resumeWaiterRef = useRef<{
    capturedCtx: AudioContext;
    timeoutId: ReturnType<typeof setTimeout>;
    cancelled: boolean;
    onStateChange: EventListenerOrEventListenerObject;
  } | null>(null);

  /**
   * Stop only the realtime WebSocket/AudioContext path without touching the HTML
   * audio element or changing generation/phase. This prevents a late close or
   * onended from calling the full stop() and killing chunk playback.
   */
  const stopRealtimeOnly = useCallback(() => {
    const ws = wsRef.current;
    wsRef.current = null;
    const ctx = audioCtxRef.current;
    audioCtxRef.current = null;
    if (ws) {
      try {
        ws.close();
      } catch {
        /* ignore */
      }
    }
    if (sourceNodeRef.current) {
      try {
        sourceNodeRef.current.stop();
        sourceNodeRef.current.disconnect();
      } catch {
        /* ignore */
      }
      sourceNodeRef.current = null;
    }
    if (ctx) {
      try {
        void ctx.close();
      } catch {
        /* ignore */
      }
    }
    if (dcRef.current) {
      try {
        dcRef.current.close();
      } catch {
        /* ignore */
      }
      dcRef.current = null;
    }
    if (pcRef.current) {
      try {
        pcRef.current.close();
      } catch {
        /* ignore */
      }
      pcRef.current = null;
    }
  }, []);

  /** Open an xAI Realtime WebSocket and stream PCM16 deltas to the provided AudioContext. */
  const startRealtimeSession = useCallback(
    (token: string, script: string, audioCtx: AudioContext) => {
      const subprotocol = `xai-client-secret.${token}`;
      const url = "wss://api.x.ai/v1/realtime?model=grok-voice-latest";
      const ws = new WebSocket(url, subprotocol);
      wsRef.current = ws;

      let nextStartTime = audioCtx.currentTime + 0.05;
      let doneReceived = false;
      let lastEndTime = 0;

      const isCurrent = () => audioCtxRef.current === audioCtx;

      const tryStop = () => {
        if (!isCurrent()) return;
        if (doneReceived && audioCtx.currentTime >= lastEndTime - 0.01) {
          stopRef.current();
        }
      };

      const onOpen = () => {
        ws.send(
          JSON.stringify({
            type: "session.update",
            session: {
              voice: voiceRef.current || readStoredTtsVoice() || DEFAULT_TTS_VOICE_ID,
              instructions:
                "Read the supplied text aloud exactly as written. Do not paraphrase. Do not add words.",
              audio: {
                output: { format: { type: "audio/pcm", rate: 24000 } },
              },
            },
          }),
        );
        ws.send(
          JSON.stringify({
            type: "conversation.item.create",
            item: {
              type: "message",
              role: "user",
              content: [{ type: "input_text", text: script }],
            },
          }),
        );
        ws.send(JSON.stringify({ type: "response.create" }));
      };

      const onMessage = (event: MessageEvent) => {
        if (!isCurrent()) return;
        try {
          const msg = JSON.parse(event.data);
          if (
            msg.type === "response.output_audio.delta" ||
            msg.type === "response.audio.delta"
          ) {
            const delta = msg.delta ?? msg.output_audio?.delta;
            if (delta) {
              const pcmData = base64ToUint8Array(delta);
              const floatData = pcm16ToFloat32(pcmData);
              const audioBuffer = audioCtx.createBuffer(1, floatData.length, 24000);
              audioBuffer.getChannelData(0).set(floatData);

              const source = audioCtx.createBufferSource();
              source.buffer = audioBuffer;
              source.connect(audioCtx.destination);

              const startTime = Math.max(audioCtx.currentTime + 0.05, nextStartTime);
              source.start(startTime);
              nextStartTime = startTime + audioBuffer.duration;
              lastEndTime = nextStartTime;

              source.onended = () => {
                tryStop();
              };
            }
          } else if (
            msg.type === "response.output_audio.done" ||
            msg.type === "response.audio.done"
          ) {
            doneReceived = true;
            tryStop();
          } else if (msg.type === "error") {
            if (wsRef.current === ws) wsRef.current = null;
            ws.close();
            showTtsErrorToast(new Error(msg.error?.message || "Realtime API error"));
          }
        } catch {
          /* ignore non-JSON messages */
        }
      };

      const onError = () => {
        if (!isCurrent()) return;
        if (wsRef.current === ws) wsRef.current = null;
        showTtsErrorToast(new Error("WebSocket error"));
      };

      const onClose = () => {
        if (!isCurrent()) return;
        if (wsRef.current === ws) wsRef.current = null;
        doneReceived = true;
        tryStop();
      };

      ws.addEventListener("open", onOpen, { once: true });
      ws.addEventListener("message", onMessage);
      ws.addEventListener("error", onError, { once: true });
      ws.addEventListener("close", onClose, { once: true });
    },
    [stopRef, voiceRef],
  );

  const cancelResumeWaiter = useCallback(() => {
    // Cancel any pending resume waiter so it cannot call beginPlayback() after stop().
    if (resumeWaiterRef.current) {
      clearTimeout(resumeWaiterRef.current.timeoutId);
      resumeWaiterRef.current.cancelled = true;
      const { capturedCtx, onStateChange } = resumeWaiterRef.current;
      if (onStateChange) {
        capturedCtx.removeEventListener("statechange", onStateChange);
      }
      resumeWaiterRef.current = null;
    }
  }, []);

  return {
    pcRef,
    dcRef,
    wsRef,
    audioCtxRef,
    sourceNodeRef,
    resumeWaiterRef,
    startRealtimeSession,
    stopRealtimeOnly,
    cancelResumeWaiter,
  };
}
