/** Junior composer clip STT. Record → POST /api/v1/stt. Never log audio. */

export const MIC_BLOCKED_TOAST = "Microphone blocked";
export const MAX_CLIP_MS = 60_000;
export const MIN_CLIP_BYTES = 64;

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

export function micDeniedMessage(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError" || error.name === "SecurityError") {
      return MIC_BLOCKED_TOAST;
    }
    if (error.name === "NotFoundError") return "No microphone found.";
  }
  return error instanceof Error && error.message.trim() ? error.message : MIC_BLOCKED_TOAST;
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

export async function startMicClip(opts?: { maxMs?: number; onAutoStop?: () => void }): Promise<MicClipSession> {
  requireSecureMic();
  if (!navigator.mediaDevices?.getUserMedia) {
    throw new Error("Microphone is not available");
  }
  const stream = await navigator.mediaDevices.getUserMedia({ audio: true, video: false });
  const mime = pickRecorderMime();
  const chunks: BlobPart[] = [];
  let recorder: MediaRecorder | null = null;
  const AudioCtx =
    window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  let context: AudioContext | null = AudioCtx ? new AudioCtx() : null;
  const pcmChunks: ArrayBuffer[] = [];
  let processor: ScriptProcessorNode | null = null;
  let stopped = false;
  let timer = 0;

  const cleanup = () => {
    if (timer) window.clearTimeout(timer);
    timer = 0;
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

  if (typeof MediaRecorder !== "undefined") {
    recorder = mime ? new MediaRecorder(stream, { mimeType: mime }) : new MediaRecorder(stream);
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunks.push(event.data);
    };
    recorder.start(250);
  }

  let result: Promise<Blob> | null = null;
  const finish = (aborted: boolean) => {
    if (result) return result;
    result = new Promise<Blob>((resolve) => {
      stopped = true;
      const done = () => {
        cleanup();
        if (aborted) {
          resolve(new Blob());
          return;
        }
        const recorded = new Blob(chunks, { type: recorder?.mimeType || mime || "audio/webm" });
        if (pcmChunks.length) {
          const total = pcmChunks.reduce((sum, part) => sum + part.byteLength, 0);
          const pcm = new Uint8Array(total);
          let offset = 0;
          for (const part of pcmChunks) {
            pcm.set(new Uint8Array(part), offset);
            offset += part.byteLength;
          }
          if (pcm.byteLength >= MIN_CLIP_BYTES) {
            const copy = pcm.buffer.slice(pcm.byteOffset, pcm.byteOffset + pcm.byteLength);
            resolve(encodeWavPcm16(copy, 16000));
            return;
          }
        }
        resolve(recorded);
      };
      if (recorder && recorder.state !== "inactive") {
        recorder.onstop = () => done();
        try {
          recorder.stop();
        } catch {
          done();
        }
      } else {
        done();
      }
    });
    return result;
  };

  timer = window.setTimeout(() => {
    if (opts?.onAutoStop) opts.onAutoStop();
    else void finish(false);
  }, opts?.maxMs ?? MAX_CLIP_MS);

  return {
    stop: () => finish(false),
    abort: () => {
      void finish(true);
    },
  };
}
