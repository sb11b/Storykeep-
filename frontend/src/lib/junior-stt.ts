/** Junior composer clip STT. Record → POST /api/v1/stt. Never log audio. */

export const MIN_CLIP_BYTES = 64;
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
  "audio/ogg;codecs=opus",
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

export async function startMicClip(opts?: { onPermissionRevoked?: () => void }): Promise<MicClipSession> {
  requireSecureMic();
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone is not available");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  const mime = pickRecorderMime();
  const chunks: BlobPart[] = [];
  let recorder: MediaRecorder | null = null;
  const canRecord = typeof MediaRecorder !== "undefined";
  const AudioCtx =
    window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  let context: AudioContext | null = !canRecord && AudioCtx ? new AudioCtx() : null;
  const pcmChunks: ArrayBuffer[] = [];
  let processor: ScriptProcessorNode | null = null;
  let stopped = false;
  let listening = true;
  let restartTimer = 0;
  let lastRestartAt = 0;
  let restartDelay = 0;
  let finishResolve: ((blob: Blob) => void) | null = null;

  const clearRestart = () => {
    if (restartTimer) window.clearTimeout(restartTimer);
    restartTimer = 0;
  };

  const streamLive = () => stream.getTracks().some((track) => track.readyState === "live");

  const cleanup = () => {
    clearRestart();
    try {
      processor?.disconnect();
    } catch {
      /* ignore */
    }
    processor = null;
    stream.getTracks().forEach((track) => track.stop());
    if (context) void context.close();
    context = null;
  };

  const blobFromChunks = () => new Blob(chunks, { type: recorder?.mimeType || mime || "audio/webm" });

  const pcmBlob = () => {
    if (!pcmChunks.length) return null;
    const total = pcmChunks.reduce((sum, part) => sum + part.byteLength, 0);
    const pcm = new Uint8Array(total);
    let offset = 0;
    for (const part of pcmChunks) {
      pcm.set(new Uint8Array(part), offset);
      offset += part.byteLength;
    }
    if (pcm.byteLength < MIN_CLIP_BYTES) return null;
    const copy = pcm.buffer.slice(pcm.byteOffset, pcm.byteOffset + pcm.byteLength);
    return encodeWavPcm16(copy, 16000);
  };

  const settle = (aborted: boolean) => {
    cleanup();
    if (!finishResolve) return;
    const resolve = finishResolve;
    finishResolve = null;
    if (aborted) {
      resolve(new Blob());
      return;
    }
    resolve(pcmBlob() || blobFromChunks());
  };

  const revoke = () => {
    if (stopped) return;
    stopped = true;
    listening = false;
    settle(true);
    opts?.onPermissionRevoked?.();
  };

  if (context) {
    if (context.state === "suspended") await context.resume();
    const source = context.createMediaStreamSource(stream);
    processor = context.createScriptProcessor(4096, 1, 1);
    processor.onaudioprocess = (event) => {
      if (stopped) return;
      pcmChunks.push(floatToPcm16(downsample(event.inputBuffer.getChannelData(0), context!.sampleRate, 16000)));
    };
    const mute = context.createGain();
    mute.gain.value = 0;
    source.connect(processor);
    processor.connect(mute);
    mute.connect(context.destination);
  }

  function scheduleRestart(fromError: boolean) {
    if (stopped || !shouldRestartMic(listening, "engine")) return;
    if (!streamLive()) {
      revoke();
      return;
    }
    const now = Date.now();
    restartDelay = nextMicRestartDelay({
      fromError,
      prevDelayMs: restartDelay,
      elapsedSinceRestartMs: lastRestartAt ? now - lastRestartAt : MIC_RESTART_MIN_GAP_MS,
    });
    lastRestartAt = now;
    clearRestart();
    restartTimer = window.setTimeout(() => {
      restartTimer = 0;
      if (stopped) return;
      bindRecorder();
    }, restartDelay);
  }

  function bindRecorder() {
    if (stopped || !canRecord || !streamLive()) return;
    try {
      recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    } catch {
      scheduleRestart(true);
      return;
    }
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunks.push(event.data);
    };
    recorder.onstart = () => {
      restartDelay = 0;
    };
    recorder.onerror = () => {
      if (stopped) return;
      scheduleRestart(true);
    };
    recorder.onstop = () => {
      if (stopped) {
        settle(false);
        return;
      }
      if (!shouldRestartMic(listening, "engine") || !streamLive()) {
        revoke();
        return;
      }
      scheduleRestart(false);
    };
    try {
      recorder.start(250);
    } catch {
      scheduleRestart(true);
    }
  }

  stream.getTracks().forEach((track) => {
    track.addEventListener("ended", () => {
      if (stopped) return;
      revoke();
    });
  });

  if (canRecord) bindRecorder();

  let result: Promise<Blob> | null = null;
  const finish = (aborted: boolean) => {
    if (result) return result;
    listening = false;
    stopped = true;
    clearRestart();
    result = new Promise<Blob>((resolve) => {
      finishResolve = (blob) => resolve(blob);
      if (aborted) {
        if (recorder && recorder.state !== "inactive") {
          try {
            recorder.stop();
          } catch {
            /* ignore */
          }
        }
        settle(true);
        return;
      }
      if (recorder && recorder.state !== "inactive") {
        try {
          recorder.stop();
        } catch {
          settle(false);
        }
        return;
      }
      settle(false);
    });
    return result;
  };

  return {
    stop: () => finish(false),
    abort: () => {
      void finish(true);
    },
  };
}
