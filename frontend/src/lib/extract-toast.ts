import { toast } from "sonner";

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

export function showExtractToast({ ok, upgraded, keptPrevious }: ExtractToastInput) {
  if (ok === false || (!upgraded && !keptPrevious)) {
    toast.error(EXTRACT_MESSAGES.failed);
    return;
  }
  if (keptPrevious && !upgraded) {
    toast.message(EXTRACT_MESSAGES.dekKept);
    return;
  }
  toast.success(EXTRACT_MESSAGES.success);
}
