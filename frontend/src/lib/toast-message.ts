import { toast } from "sonner";
import { ApiError } from "@/lib/api";
import { httpErrorFallback } from "@/lib/api-errors";

export function nonEmptyMessage(message: string | null | undefined, fallback: string): string {
  const text = message?.trim();
  return text || fallback;
}

export { httpErrorFallback };

export function messageFromApiError(error: unknown, fallback: string): string {
  if (error instanceof ApiError) {
    return nonEmptyMessage(error.message, httpErrorFallback(error.status));
  }
  if (error instanceof Error) {
    return nonEmptyMessage(error.message, fallback);
  }
  return fallback;
}

export function toastError(message: string | null | undefined, status?: number): void {
  const fallback = typeof status === "number" ? httpErrorFallback(status) : "Something went wrong.";
  const text = nonEmptyMessage(message, fallback);
  toast.error(text);
}

export function toastErrorFromUnknown(error: unknown, fallback: string): void {
  if (error instanceof ApiError) {
    toastError(error.message, error.status);
    return;
  }
  toastError(messageFromApiError(error, fallback));
}
