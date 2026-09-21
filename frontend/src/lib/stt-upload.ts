/** Prepare captured mic blobs for StoryKeep /api/stt upload — no transcoding. */

export const STT_MODEL = "grok-voice-transcribe-2.0";

export function sttUploadFilename(mime: string): string {
  const type = (mime || "").split(";", 1)[0].trim().toLowerCase();
  if (type.includes("wav")) return "audio.wav";
  if (type.includes("mp4") || type.includes("m4a")) return "audio.mp4";
  if (type.includes("webm")) return "audio.webm";
  if (type.includes("ogg")) return "audio.ogg";
  return "audio.webm";
}

export function formatSttBlobHint(blob: Blob): string {
  const ext = sttUploadFilename(blob.type || "").replace(/^audio\./, "");
  const kb = Math.max(1, Math.round(blob.size / 1024));
  return `${ext} ${kb}kb`;
}

export function formatSttEmptyHint(input: { mime?: string | null; bytes?: number | null; blob?: Blob }): string {
  const mimeRaw = input.mime || input.blob?.type || "unknown";
  const ext = sttUploadFilename(mimeRaw).replace(/^audio\./, "");
  const size = input.bytes ?? input.blob?.size ?? 0;
  const kb = Math.max(1, Math.round(size / 1024));
  return `STT empty (${ext} ${kb}kb)`;
}

/** Pass native MediaRecorder blob through with matching filename and mime. */
export function prepareSttUpload(blob: Blob): { blob: Blob; filename: string; mime: string } {
  const rawType = (blob.type || "audio/webm").split(";", 1)[0].trim().toLowerCase() || "audio/webm";
  const mime =
    rawType === "audio/wave" || rawType === "audio/x-wav"
      ? "audio/wav"
      : rawType.startsWith("audio/")
        ? rawType
        : "audio/webm";
  return { blob, filename: sttUploadFilename(mime), mime };
}
