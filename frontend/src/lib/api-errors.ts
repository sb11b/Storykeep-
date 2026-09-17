export function httpErrorFallback(status: number): string {
  return `Something went wrong (HTTP ${status}).`;
}

const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export function isUuid(value: string | null | undefined): boolean {
  return Boolean(value && UUID_RE.test(value.trim()));
}

export function isFeedId(value: string | null | undefined): boolean {
  return isUuid(value);
}

function isPydanticUuidDump(text: string): boolean {
  return /valid uuid/i.test(text);
}

function locHas(item: unknown, name: string): boolean {
  if (!item || typeof item !== "object") return false;
  const loc = (item as { loc?: unknown }).loc;
  return Array.isArray(loc) && loc.some((part) => part === name);
}

function locHasFeedId(item: unknown): boolean {
  return locHas(item, "feed_id");
}

function locHasConversationId(item: unknown): boolean {
  return locHas(item, "conversation_id");
}

function locHasProfileId(item: unknown): boolean {
  return locHas(item, "avatar_media_id") || locHas(item, "media_id");
}

export const INVALID_ID_TOAST = "Invalid id";

export function profileUuidToast(status: number, message: string): string | null {
  if (status !== 422 && status !== 400) return null;
  const text = message.trim();
  if (!text || /invalid id|valid uuid|invalid request|invalid feed|found `/i.test(text)) {
    return INVALID_ID_TOAST;
  }
  return null;
}

function messageFromUnknown(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) {
    const text = value.trim();
    if (isPydanticUuidDump(text)) return "Invalid feed";
    return text;
  }
  if (Array.isArray(value) && value.length > 0) {
    const uuidType = (item: unknown) =>
      Boolean(item && typeof item === "object" && String((item as { type?: unknown }).type || "").startsWith("uuid"));
    if (value.some((item) => locHasFeedId(item) && uuidType(item))) return "Invalid feed";
    if (value.some((item) => locHasConversationId(item) && uuidType(item))) return "Invalid chat";
    if (value.some((item) => locHasProfileId(item) && uuidType(item))) return "Invalid id";
    const parts = value
      .map((item) => {
        if (typeof item === "string" && item.trim()) return item.trim();
        if (item && typeof item === "object" && "msg" in item) {
          const msg = (item as { msg?: unknown }).msg;
          return typeof msg === "string" && msg.trim() ? msg.trim() : null;
        }
        return null;
      })
      .filter(Boolean) as string[];
    if (parts.some(isPydanticUuidDump)) return "Invalid request";
    if (parts.length) return parts.join("; ");
  }
  if (value && typeof value === "object") {
    const rec = value as Record<string, unknown>;
    if (typeof rec.message === "string" && rec.message.trim()) return rec.message.trim();
  }
  return null;
}

export function parseErrorPayload(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const body = data as Record<string, unknown>;
  for (const key of ["message", "detail", "error"]) {
    const parsed = messageFromUnknown(body[key]);
    if (parsed) return parsed;
  }
  return null;
}

export function shrinkConfirmMessage(currentChars: number, incomingChars: number): string {
  return `This save is much shorter (${incomingChars} vs ${currentChars}). Save anyway?`;
}

export function restoreCharsConfirm(charCount: number): string {
  return `Restore ${charCount} characters?`;
}

export function isNoteShrinkMessage(message: string): boolean {
  return /this save is much shorter/i.test(message);
}
