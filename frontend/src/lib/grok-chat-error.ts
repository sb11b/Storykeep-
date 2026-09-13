import { httpErrorFallback } from "@/lib/api-errors";

export function formatChatError(status: number, detail: string): string {
  const message = detail.trim() || httpErrorFallback(status);
  return `Chat failed (HTTP ${status}): ${message}`;
}
