import { toast } from "sonner";
import { ApiError } from "@/lib/api";
import { messageFromApiError, nonEmptyMessage, toastError } from "@/lib/toast-message";

export const EXTRACT_MESSAGES = {
  success: "Updated from the page.",
  dekKept: "Page had no full article; kept the short feed text.",
  failed: "Extract failed; previous text kept.",
} as const;

type ExtractToastInput = {
  message?: string | null;
  ok?: boolean;
  upgraded: boolean;
  keptPrevious: boolean;
};

export function extractFailureMessage(message?: string | null): string {
  return nonEmptyMessage(message, EXTRACT_MESSAGES.failed);
}

export function logExtractFailed(error: unknown, message: string): void {
  console.error("extract-failed:", message, error);
}

export function showExtractFailed(message?: string | null, error?: unknown): void {
  const text = extractFailureMessage(message);
  logExtractFailed(error ?? text, text);
  toastError(text);
}

export function showExtractToast({ ok, upgraded, keptPrevious, message }: ExtractToastInput) {
  if (ok === false || (!upgraded && !keptPrevious)) {
    showExtractFailed(message);
    return;
  }
  if (keptPrevious && !upgraded) {
    toast.message(nonEmptyMessage(EXTRACT_MESSAGES.dekKept, EXTRACT_MESSAGES.dekKept));
    return;
  }
  toast.success(EXTRACT_MESSAGES.success);
}

export function showExtractCaughtError(error: unknown): void {
  const text =
    error instanceof ApiError
      ? nonEmptyMessage(error.message, EXTRACT_MESSAGES.failed)
      : messageFromApiError(error, EXTRACT_MESSAGES.failed);
  showExtractFailed(text, error);
}
