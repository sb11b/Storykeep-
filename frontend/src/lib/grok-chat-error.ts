import { httpErrorFallback } from "@/lib/api-errors";

export function readableXaiToast(message: string): string {
  const stripped = message
    .replace(/^Chat failed \(HTTP \d+\):\s*/i, "")
    .replace(/^xAI HTTP \d+:\s*/i, "")
    .trim();
  return stripped || message;
}

/** FastAPI 422 on a tiny maxlength — never show a blank validation dump. */
export function isOversizedPasteHttp(status: number, detail: string): boolean {
  if (status === 413) return true;
  if (status === 422 && /at most \d+ character/i.test(detail)) return true;
  if (status === 400 && /too long|over the cap|payload is too large/i.test(detail)) return true;
  if (status === 502 && /over the cap|payload too large|entity too large/i.test(detail)) return true;
  return false;
}

export function formatChatError(status: number, detail: string, assistantName?: string): string {
  const message = detail.trim() || httpErrorFallback(status);
  return `Chat failed (HTTP ${status}): ${withAssistantName(message, assistantName)}`;
}

/** Legacy idle toast; long replies use server text with minutes when needed. */
export const CHAT_IDLE_TIMEOUT_TOAST = "Timed out after 60s.";

export function chatTimeoutToast(status: number, message: string): string | null {
  if (status !== 504) return `HTTP ${status}`;
  if (/xAI silent/i.test(message)) return "xAI silent";
  if (/waiting for the next token/i.test(message)) return message;
  if (/timed out after/i.test(message)) return message;
  return `HTTP ${status}`;
}

/** The backend names the upstream model; the UI shows the pane's name instead. */
export function withAssistantName(message: string, assistantName?: string): string {
  if (!assistantName) return message;
  return message
    .replace(/Larry \(the asparagus\)/g, assistantName)
    .replace(/\bLarry\b/g, assistantName)
    .replace(/\bGrok\b/g, assistantName);
}
