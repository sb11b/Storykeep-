import { isUuid } from "@/lib/api-errors";

export const CHAT_CREATE_TIMEOUT_TOAST = "Chat create timed out — retry";
export const INVALID_CHAT_TOAST = "Invalid chat";

const RESERVED_CONVERSATION_PATHS = new Set(["new", "refresh", ""]);

export function isConversationId(value: string | null | undefined): boolean {
  return isUuid(value);
}

export function conversationIdForRequest(value: string | null | undefined): string | null {
  if (!isConversationId(value)) return null;
  return value!.trim();
}

export function isReservedConversationPath(value: string | null | undefined): boolean {
  const trimmed = (value || "").trim().toLowerCase();
  return RESERVED_CONVERSATION_PATHS.has(trimmed);
}

export function chatCreateErrorToast(status: number, message: string): string | null {
  const text = message.trim();
  if (status === 504 && /chat create timed out/i.test(text)) {
    return CHAT_CREATE_TIMEOUT_TOAST;
  }
  if (status === 422 || status === 400) {
    if (!text || /invalid chat|valid uuid|invalid request|found `/i.test(text)) {
      return INVALID_CHAT_TOAST;
    }
  }
  return null;
}
