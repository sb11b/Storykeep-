/** Junior / dictation mic chrome. Keep copy identical in the pane and toasts. */

export const MIC_LIVE = "Mic live";
export const MIC_IDLE = "Mic idle";
export const MIC_DROPPED_TOAST = "Mic dropped — tap to resume.";
export const MIC_DENIED_TOAST = "Microphone blocked";

export function micDeniedMessage(error: unknown): string {
  if (error instanceof DOMException) {
    if (error.name === "NotAllowedError" || error.name === "PermissionDeniedError" || error.name === "SecurityError") {
      return MIC_DENIED_TOAST;
    }
    if (error.name === "NotFoundError") return "No microphone found.";
  }
  return error instanceof Error && error.message.trim() ? error.message : MIC_DENIED_TOAST;
}
