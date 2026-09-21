/** Junior composer clip STT. Record → POST /api/v1/stt. Never log audio. */

export const MIN_CLIP_BYTES = 64;
/** Minimum captured clip size before POSTing STT. */
export const MIN_CAPTURE_BYTES = 256;
export const NO_AUDIO_CAPTURED = "No audio captured";
export const MIC_PERMISSION_DENIED = "Mic permission denied";

/** Tight-loop guard when MediaRecorder / SpeechRecognition ends on its own. */
export const MIC_RESTART_MIN_GAP_MS = 400;
export const MIC_RESTART_MAX_MS = 8_000;
export const MIC_RESTART_ERROR_MS = 200;

export type MicEndReason = "user" | "permission" | "engine";

/** Restart the same session only while the user still has listening latched on. */
export function shouldRestartMic(listening: boolean, reason: MicEndReason): boolean {
  return listening && reason === "engine";
}

export function nextMicRestartDelay(input: {
  fromError: boolean;
  prevDelayMs: number;
  elapsedSinceRestartMs: number;
}): number {
  if (input.fromError || input.elapsedSinceRestartMs < MIC_RESTART_MIN_GAP_MS) {
    const base = input.prevDelayMs > 0 ? input.prevDelayMs : MIC_RESTART_ERROR_MS;
    return Math.min(base * 2, MIC_RESTART_MAX_MS);
  }
  return 0;
}

const RECORDER_TYPES = [
  "audio/webm;codecs=opus",
  "audio/webm",
  "audio/mp4",
  "audio/wav",
];

export function pickRecorderMime(supported?: (type: string) => boolean): string {
  const check =
    supported ||
    ((type: string) => (typeof MediaRecorder !== "undefined" ? MediaRecorder.isTypeSupported(type) : false));
  return RECORDER_TYPES.find((type) => check(type)) || "";
}

export function clipFilename(mime: string): string {
  const type = (mime || "").split(";", 1)[0].trim().toLowerCase();
  if (type.includes("wav")) return "clip.wav";
  if (type.includes("ogg")) return "clip.ogg";
  if (type.includes("mp4") || type.includes("m4a")) return "clip.m4a";
  if (type.includes("mpeg") || type.includes("mp3")) return "clip.mp3";
  return "clip.webm";
}

export function sttFailToast(status: number | string, detail?: string): string {
  const text = (detail || "").trim();
  if (text.toLowerCase() === "empty blob" || text.toLowerCase().includes("empty blob")) {
    return "STT failed (empty blob)";
  }
  if (text && /^STT failed/i.test(text)) return text;
  const code = typeof status === "number" ? status : Number.parseInt(String(status), 10);
  if (Number.isFinite(code) && code > 0) {
    return `STT failed (${code})`;
  }
  return text || "STT failed";
}

export function requireSecureMic(): void {
  if (typeof window !== "undefined" && !window.isSecureContext) {
    throw new DOMException("HTTPS required", "SecurityError");
  }
}

function writeString(view: DataView, offset: number, value: string) {
  for (let i = 0; i < value.length; i += 1) view.setUint8(offset + i, value.charCodeAt(i));
}

export function encodeWavPcm16(pcm: ArrayBuffer, sampleRate: number): Blob {
  const bytes = new Uint8Array(pcm);
  const buffer = new ArrayBuffer(44 + bytes.byteLength);
  const view = new DataView(buffer);
  writeString(view, 0, "RIFF");
  view.setUint32(4, 36 + bytes.byteLength, true);
  writeString(view, 8, "WAVE");
  writeString(view, 12, "fmt ");
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);
  view.setUint16(22, 1, true);
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true);
  view.setUint16(32, 2, true);
  view.setUint16(34, 16, true);
  writeString(view, 36, "data");
  view.setUint32(40, bytes.byteLength, true);
  new Uint8Array(buffer, 44).set(bytes);
  return new Blob([buffer], { type: "audio/wav" });
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

export type MicClipSession = {
  stop: () => Promise<Blob>;
  abort: () => void;
};

/** STS end-of-utterance silence window (ms). */
export const STS_SILENCE_MS = 1_500;
export const STS_SPEECH_THRESHOLD = 0.015;
export const STS_MIN_SPEECH_MS = 250;

export type MicClipOptions = {
  onPermissionRevoked?: () => void;
  /** Fires once after speech then ~STS_SILENCE_MS of silence. */
  onSilenceEnd?: () => void;
  silenceMs?: number;
};

type SilenceMonitor = { stop: () => void };

/** Analyser RMS VAD — speech detected, then silence triggers once. */
export function attachSilenceMonitor(
  stream: MediaStream,
  opts: { onSilenceEnd: () => void; silenceMs?: number },
): SilenceMonitor {
  const AudioCtx =
    window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtx) return { stop: () => {} };

  const context = new AudioCtx();
  const source = context.createMediaStreamSource(stream);
  const analyser = context.createAnalyser();
  analyser.fftSize = 2048;
  source.connect(analyser);
  const samples = new Float32Array(analyser.fftSize);
  const silenceMs = opts.silenceMs ?? STS_SILENCE_MS;
  let speechDetected = false;
  let speechStart = 0;
  let silenceStart: number | null = null;
  let fired = false;
  let rafId = 0;
  let stopped = false;

  const tick = () => {
    if (stopped || fired) return;
    analyser.getFloatTimeDomainData(samples);
    let sum = 0;
    for (let i = 0; i < samples.length; i += 1) sum += samples[i]! * samples[i]!;
    const rms = Math.sqrt(sum / samples.length);
    const now = performance.now();
    if (rms >= STS_SPEECH_THRESHOLD) {
      if (!speechDetected) {
        speechDetected = true;
        speechStart = now;
        console.log("junior-stt", { action: "speech-start", rms: Number(rms.toFixed(4)) });
      }
      silenceStart = null;
    } else if (speechDetected && now - speechStart >= STS_MIN_SPEECH_MS) {
      if (silenceStart == null) silenceStart = now;
      else if (now - silenceStart >= silenceMs) {
        fired = true;
        console.log("junior-stt", {
          action: "silence-trigger",
          rms: Number(rms.toFixed(4)),
          silenceMs: Math.round(now - silenceStart),
        });
        opts.onSilenceEnd();
        return;
      }
    }
    rafId = requestAnimationFrame(tick);
  };

  void context.resume().then(() => {
    if (!stopped) rafId = requestAnimationFrame(tick);
  });

  return {
    stop: () => {
      stopped = true;
      if (rafId) cancelAnimationFrame(rafId);
      try {
        source.disconnect();
        analyser.disconnect();
      } catch {
        /* ignore */
      }
      void context.close();
    },
  };
}

function wrapMicSession(session: MicClipSession, monitor?: SilenceMonitor): MicClipSession {
  return {
    stop: async () => {
      monitor?.stop();
      return session.stop();
    },
    abort: () => {
      monitor?.stop();
      session.abort();
    },
  };
}

/** Real PCM WAV when MediaRecorder cannot use webm/mp4. */
async function startPcmWavClip(
  stream: MediaStream,
  opts?: { onPermissionRevoked?: () => void },
): Promise<MicClipSession> {
  const AudioCtx =
    window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtx) throw new Error("MediaRecorder is not available");
  const context = new AudioCtx();
  if (context.state === "suspended") await context.resume();
  const pcmChunks: ArrayBuffer[] = [];
  let aborted = false;
  let stopPromise: Promise<Blob> | null = null;

  const source = context.createMediaStreamSource(stream);
  const processor = context.createScriptProcessor(4096, 1, 1);
  processor.onaudioprocess = (event) => {
    if (aborted) return;
    pcmChunks.push(floatToPcm16(downsample(event.inputBuffer.getChannelData(0), context.sampleRate, 16000)));
  };
  const mute = context.createGain();
  mute.gain.value = 0;
  source.connect(processor);
  processor.connect(mute);
  mute.connect(context.destination);

  stream.getTracks().forEach((track) => {
    track.addEventListener("ended", () => opts?.onPermissionRevoked?.());
  });

  const buildBlob = () => {
    if (!pcmChunks.length) return new Blob([], { type: "audio/wav" });
    const total = pcmChunks.reduce((sum, part) => sum + part.byteLength, 0);
    const pcm = new Uint8Array(total);
    let offset = 0;
    for (const part of pcmChunks) {
      pcm.set(new Uint8Array(part), offset);
      offset += part.byteLength;
    }
    const copy = pcm.buffer.slice(pcm.byteOffset, pcm.byteOffset + pcm.byteLength);
    return encodeWavPcm16(copy, 16000);
  };

  const cleanup = () => {
    try {
      processor.disconnect();
      source.disconnect();
      mute.disconnect();
    } catch {
      /* ignore */
    }
    stopStreamTracks(stream);
    void context.close();
  };

  return {
    stop: () => {
      if (stopPromise) return stopPromise;
      stopPromise = Promise.resolve().then(() => {
        aborted = true;
        cleanup();
        return buildBlob();
      });
      return stopPromise;
    },
    abort: () => {
      aborted = true;
      cleanup();
      stopPromise = Promise.resolve(new Blob());
    },
  };
}

type StreamSink = {
  close: () => void;
};

/** Chrome/Safari often yield empty MediaRecorder blobs unless the stream is actively consumed. */
async function attachStreamSink(stream: MediaStream): Promise<StreamSink> {
  const AudioCtx =
    window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (AudioCtx) {
    const context = new AudioCtx();
    if (context.state === "suspended") await context.resume();
    const source = context.createMediaStreamSource(stream);
    const mute = context.createGain();
    mute.gain.value = 0;
    source.connect(mute);
    mute.connect(context.destination);
    return {
      close: () => {
        try {
          source.disconnect();
          mute.disconnect();
        } catch {
          /* ignore */
        }
        void context.close();
      },
    };
  }
  const sink = document.createElement("audio");
  sink.srcObject = stream;
  sink.muted = true;
  sink.setAttribute("playsinline", "true");
  void sink.play().catch(() => {});
  return {
    close: () => {
      sink.pause();
      sink.srcObject = null;
    },
  };
}

function stopStreamTracks(stream: MediaStream) {
  stream.getTracks().forEach((track) => track.stop());
}

const RECORDER_STOP_TIMEOUT_MS = 2_000;

/** Wait for final dataavailable + onstop after recorder.stop(). */
function waitForRecorderClip(
  recorder: MediaRecorder,
  chunks: BlobPart[],
  stream: MediaStream,
  sink: StreamSink,
): Promise<Blob> {
  const mime = recorder.mimeType || "audio/webm";

  const build = () => new Blob(chunks, { type: mime });

  if (recorder.state === "inactive") {
    sink.close();
    stopStreamTracks(stream);
    return Promise.resolve(build());
  }

  return new Promise<Blob>((resolve) => {
    let settled = false;
    let sawStop = false;

    const finish = () => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      sink.close();
      stopStreamTracks(stream);
      resolve(build());
    };

    const onData = (event: BlobEvent) => {
      if (event.data && event.data.size > 0) chunks.push(event.data);
    };

    const onStop = () => {
      sawStop = true;
      // Final dataavailable may land after onstop; allow one frame + a short flush.
      window.setTimeout(finish, 100);
    };

    recorder.addEventListener("dataavailable", onData);
    recorder.addEventListener("stop", onStop, { once: true });

    const timer = window.setTimeout(() => {
      if (!sawStop) recorder.removeEventListener("stop", onStop);
      recorder.removeEventListener("dataavailable", onData);
      finish();
    }, RECORDER_STOP_TIMEOUT_MS);

    try {
      if (recorder.state === "recording") {
        try {
          recorder.requestData();
        } catch {
          /* optional flush */
        }
      }
      recorder.stop();
    } catch {
      recorder.removeEventListener("dataavailable", onData);
      recorder.removeEventListener("stop", onStop);
      finish();
    }
  });
}

export async function startMicClip(opts?: MicClipOptions): Promise<MicClipSession> {
  requireSecureMic();
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone is not available");
  }
  if (typeof MediaRecorder === "undefined") {
    throw new Error("MediaRecorder is not available");
  }

  let stream: MediaStream;
  try {
    stream = await navigator.mediaDevices.getUserMedia({ audio: true });
  } catch (error) {
    if (error instanceof DOMException && (error.name === "NotAllowedError" || error.name === "PermissionDeniedError")) {
      throw new DOMException(MIC_PERMISSION_DENIED, "NotAllowedError");
    }
    throw error;
  }

  stream.getTracks().forEach((track) => {
    track.addEventListener("ended", () => opts?.onPermissionRevoked?.());
  });

  let silenceMonitor: SilenceMonitor | undefined;
  if (opts?.onSilenceEnd) {
    let silenceFired = false;
    silenceMonitor = attachSilenceMonitor(stream, {
      silenceMs: opts.silenceMs,
      onSilenceEnd: () => {
        if (silenceFired) return;
        silenceFired = true;
        opts.onSilenceEnd?.();
      },
    });
  }

  const preferredMime = pickRecorderMime();
  console.log("junior-stt", { action: "mime", chosen: preferredMime || "pcm-wav-fallback" });
  if (!preferredMime) {
    return wrapMicSession(await startPcmWavClip(stream, opts), silenceMonitor);
  }

  const sink = await attachStreamSink(stream);
  let recorder: MediaRecorder;
  try {
    recorder = new MediaRecorder(stream, { mimeType: preferredMime });
  } catch {
    sink.close();
    stopStreamTracks(stream);
    return wrapMicSession(await startPcmWavClip(stream, opts), silenceMonitor);
  }

  const chunks: BlobPart[] = [];
  recorder.ondataavailable = (event) => {
    if (event.data && event.data.size > 0) chunks.push(event.data);
  };

  let stopPromise: Promise<Blob> | null = null;
  let aborted = false;

  try {
    recorder.start(250);
  } catch {
    sink.close();
    stopStreamTracks(stream);
    return wrapMicSession(await startPcmWavClip(stream, opts), silenceMonitor);
  }

  return wrapMicSession(
    {
      stop: () => {
        if (stopPromise) return stopPromise;
        if (aborted) {
          stopPromise = Promise.resolve(new Blob([], { type: recorder.mimeType || preferredMime || "audio/webm" }));
          return stopPromise;
        }
        stopPromise = waitForRecorderClip(recorder, chunks, stream, sink);
        return stopPromise;
      },
      abort: () => {
        aborted = true;
        try {
          if (recorder.state !== "inactive") recorder.stop();
        } catch {
          /* ignore */
        }
        sink.close();
        stopStreamTracks(stream);
        stopPromise = Promise.resolve(new Blob());
      },
    },
    silenceMonitor,
  );
}
