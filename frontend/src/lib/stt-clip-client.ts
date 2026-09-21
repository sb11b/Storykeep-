import { ApiError } from "@/lib/api";
import { httpErrorFallback, parseErrorPayload } from "@/lib/api-errors";
import { formatSttBlobHint, prepareSttUpload } from "@/lib/stt-upload";

/** Match server/xAI batch STT timeout (120s). */
export const STT_CLIP_TIMEOUT_MS = 120_000;

export type TranscribeClipOptions = {
  signal?: AbortSignal;
  timeoutMs?: number;
};

export function sttEmptyToast(blob: Blob): string {
  return `STT empty (${formatSttBlobHint(blob)})`;
}

/** POST /api/v1/stt — proxy clip to xAI; never expose the API key in the browser. */
export async function transcribeClip(
  blob: Blob,
  options: TranscribeClipOptions = {},
): Promise<{ text: string }> {
  const controller = new AbortController();
  const abortFromCaller = () => controller.abort();
  if (options.signal?.aborted) controller.abort();
  else options.signal?.addEventListener("abort", abortFromCaller, { once: true });

  let timedOut = false;
  const timeoutMs = options.timeoutMs ?? STT_CLIP_TIMEOUT_MS;
  const timer = setTimeout(() => {
    timedOut = true;
    controller.abort();
  }, timeoutMs);
  let status = 0;

  const prepared = await prepareSttUpload(blob);
  const uploadBlob = prepared.blob;
  const file = new File([uploadBlob], prepared.filename, { type: prepared.mime });
  const body = new FormData();
  body.append("file", file);

  try {
    const response = await fetch("/api/v1/stt", {
      method: "POST",
      body,
      signal: controller.signal,
      credentials: "include",
      cache: "no-store",
    });
    status = response.status;
    const data = (await response.json()) as { text?: string; error?: string; detail?: string };
    if (!response.ok) {
      const detail = parseErrorPayload(data) || data.error || data.detail || httpErrorFallback(status);
      throw new ApiError(status, detail);
    }
    const text = (data.text || "").trim();
    if (!text) {
      throw new ApiError(status, sttEmptyToast(uploadBlob));
    }
    return { text };
  } catch (error) {
    if (timedOut) {
      const seconds = Math.round(timeoutMs / 1000);
      throw new ApiError(status || 408, `STT timed out after ${seconds}s.`);
    }
    throw error;
  } finally {
    clearTimeout(timer);
    options.signal?.removeEventListener("abort", abortFromCaller);
  }
}
