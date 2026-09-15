export function httpErrorFallback(status: number): string {
  return `Something went wrong (HTTP ${status}).`;
}

function messageFromUnknown(value: unknown): string | null {
  if (typeof value === "string" && value.trim()) return value.trim();
  if (Array.isArray(value) && value.length > 0) {
    const parts = value
      .map((item) => {
        if (typeof item === "string" && item.trim()) return item.trim();
        if (item && typeof item === "object" && "msg" in item) {
          const msg = (item as { msg?: unknown }).msg;
          return typeof msg === "string" && msg.trim() ? msg.trim() : null;
        }
        return null;
      })
      .filter(Boolean);
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
