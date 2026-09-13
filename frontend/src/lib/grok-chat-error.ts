import { httpErrorFallback } from "@/lib/api-errors";

export function formatChatError(status: number, detail: string, assistantName?: string): string {
  const message = detail.trim() || httpErrorFallback(status);
  return `Chat failed (HTTP ${status}): ${withAssistantName(message, assistantName)}`;
}

/** The backend names the upstream model; the UI shows the pane's name instead. */
export function withAssistantName(message: string, assistantName?: string): string {
  if (!assistantName) return message;
  return message.replace(/\bGrok\b/g, assistantName);
}
