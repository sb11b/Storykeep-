/** Prepare captured mic blobs for xAI batch STT upload. */

import { encodeWavPcm16 } from "@/lib/junior-stt";

const XAI_STT_CONTAINERS = new Set([
  "audio/wav",
  "audio/wave",
  "audio/x-wav",
  "audio/mpeg",
  "audio/mp3",
  "audio/ogg",
  "audio/opus",
  "audio/flac",
  "audio/aac",
  "audio/mp4",
  "audio/m4a",
  "audio/x-m4a",
]);

export function sttUploadFilename(mime: string): string {
  const type = (mime || "").split(";", 1)[0].trim().toLowerCase();
  if (type.includes("wav")) return "audio.wav";
  if (type.includes("ogg")) return "audio.ogg";
  if (type.includes("opus")) return "audio.opus";
  if (type.includes("mp4") || type.includes("m4a")) return "audio.mp4";
  if (type.includes("mpeg") || type.includes("mp3")) return "audio.mp3";
  if (type.includes("webm")) return "audio.webm";
  return "audio.webm";
}

export function formatSttBlobHint(blob: Blob): string {
  const ext = sttUploadFilename(blob.type || "").replace(/^audio\./, "");
  const kb = Math.max(1, Math.round(blob.size / 1024));
  return `${ext} ${kb}kb`;
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

async function containerBlobToWav(blob: Blob): Promise<Blob> {
  const AudioCtx =
    window.AudioContext || (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
  if (!AudioCtx) throw new Error("AudioContext unavailable");
  const ctx = new AudioCtx();
  try {
    if (ctx.state === "suspended") await ctx.resume();
    const decoded = await ctx.decodeAudioData(await blob.arrayBuffer());
    const mono = new Float32Array(decoded.length);
    for (let channel = 0; channel < decoded.numberOfChannels; channel += 1) {
      const data = decoded.getChannelData(channel);
      for (let i = 0; i < decoded.length; i += 1) mono[i] += data[i]! / decoded.numberOfChannels;
    }
    return encodeWavPcm16(floatToPcm16(mono), decoded.sampleRate);
  } finally {
    await ctx.close();
  }
}

/** xAI batch STT does not accept WebM containers — convert to WAV before upload. */
export async function prepareSttUpload(
  blob: Blob,
): Promise<{ blob: Blob; filename: string; mime: string }> {
  const rawType = (blob.type || "audio/webm").split(";", 1)[0].trim().toLowerCase();
  if (XAI_STT_CONTAINERS.has(rawType)) {
    const mime = rawType === "audio/wave" || rawType === "audio/x-wav" ? "audio/wav" : rawType;
    return { blob, filename: sttUploadFilename(mime), mime };
  }
  if (rawType.includes("webm") || !rawType) {
    const wav = await containerBlobToWav(blob);
    return { blob: wav, filename: "audio.wav", mime: "audio/wav" };
  }
  try {
    const wav = await containerBlobToWav(blob);
    return { blob: wav, filename: "audio.wav", mime: "audio/wav" };
  } catch {
    return { blob, filename: sttUploadFilename(rawType), mime: rawType || "audio/webm" };
  }
}
