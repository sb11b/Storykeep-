export function httpErrorFallback(status: number): string {
  return `Something went wrong (HTTP ${status}).`;
}

export function parseErrorPayload(data: unknown): string | null {
  if (!data || typeof data !== "object") return null;
  const body = data as Record<string, unknown>;
  for (const key of ["message", "detail", "error"]) {
    const value = body[key];
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
  }
  return null;
}
