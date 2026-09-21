import { ApiError } from "@/lib/api";
import { httpErrorFallback, parseErrorPayload } from "@/lib/api-errors";

/** Match server/xAI batch STT timeout (120s). */
export const STT_CLIP_TIMEOUT_MS = 120_000;

export type TranscribeClipOptions = {
  signal?: AbortSignal;
  timeoutMs?: number;
};

/** POST /api/v1/stt — proxy clip to xAI; never expose the API key in the browser. */
export async function transcribeClip(
  blob: Blob,
  filename: string,
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

  const type = (blob.type || "audio/webm").split(";", 1)[0].trim() || "audio/webm";
  const body = new FormData();
  body.append("file", blob, filename || (type.includes("wav") ? "clip.wav" : "clip.webm"));

  try {
    const response = await fetch("/api/v1/stt", {
      method: "POST",
      body,
      signal: controller.signal,
      credentials: "include",
      cache: "no-store",
    });
    status = response.status;
    if (!response.ok) {
      let detail: string | null = null;
      try {
        detail = parseErrorPayload(await response.json());
      } catch {
        /* ignore */
      }
      throw new ApiError(status, detail || httpErrorFallback(status));
    }
    const data = (await response.json()) as { text?: string };
    const text = (data.text || "").trim();
    if (!text) {
      throw new ApiError(status || 502, "STT failed (empty transcript)");
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
