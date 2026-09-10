import { toast } from "sonner";
import { ApiError } from "@/lib/api";
import { messageFromApiError, nonEmptyMessage, toastError } from "@/lib/toast-message";

export const EXTRACT_MESSAGES = {
  success: "Updated from the page.",
  failed: "Kept existing text: extract failed.",
} as const;

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

export function showExtractSuccess(message?: string | null): void {
  toast.success(nonEmptyMessage(message, EXTRACT_MESSAGES.success));
}

export function showExtractCaughtError(error: unknown): void {
  const text =
    error instanceof ApiError
      ? nonEmptyMessage(error.message, EXTRACT_MESSAGES.failed)
      : messageFromApiError(error, EXTRACT_MESSAGES.failed);
  showExtractFailed(text, error);
}
