import { toast } from "sonner";
import { ApiError } from "@/lib/api";
import { httpErrorFallback } from "@/lib/api-errors";

const TTS_ERROR_TOAST_CLASS =
  "!bg-[oklch(0.38_0.12_28)] !text-white !border-[oklch(0.32_0.1_28)] shadow-lg";

export function ttsErrorMessage(error: unknown): string {
  const status = error instanceof ApiError ? error.status : 0;
  const server =
    error instanceof ApiError && error.message.trim()
      ? error.message.trim()
      : error instanceof Error && error.message.trim()
        ? error.message.trim()
        : httpErrorFallback(status || 0);
  return `Could not read (HTTP ${status || "error"}): ${server}`;
}

/** Bottom-left toast with white text on dark red — never an empty message. */
export function showTtsErrorToast(error: unknown) {
  toast.error(ttsErrorMessage(error), {
    position: "bottom-left",
    duration: 8000,
    classNames: {
      toast: TTS_ERROR_TOAST_CLASS,
      title: "!text-white",
      description: "!text-white/90",
    },
  });
}
