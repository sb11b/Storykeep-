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

export function showExtractToast({ message, ok, upgraded, keptPrevious }: ExtractToastInput) {
  const resolved =
    message?.trim() ||
    (upgraded
      ? EXTRACT_MESSAGES.success
      : keptPrevious
        ? EXTRACT_MESSAGES.dekKept
        : EXTRACT_MESSAGES.failed);

  if (ok === false || (!upgraded && !keptPrevious)) {
    toast.error(resolved);
    return;
  }
  if (keptPrevious && !upgraded) {
    toast.message(resolved);
    return;
  }
  toast.success(resolved);
}
