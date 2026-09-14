import { ApiError } from "@/lib/api";
import { httpErrorFallback, parseErrorPayload } from "@/lib/api-errors";

const UUID = /^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$/;
const DOCX_TYPE = "application/vnd.openxmlformats-officedocument.wordprocessingml.document";

export function isPersistedMessageId(id: string | null | undefined): boolean {
  return UUID.test((id || "").trim());
}

export function filenameFromContentDisposition(header: string | null, fallback = "Junior-reply.docx"): string {
  const value = header || "";
  const star = value.match(/filename\*=UTF-8''([^;]+)/i);
  if (star?.[1]) {
    try {
      return decodeURIComponent(star[1].trim());
    } catch {
      /* fall through */
    }
  }
  const quoted = value.match(/filename="([^"]+)"/i);
  if (quoted?.[1]) return quoted[1];
  const plain = value.match(/filename=([^;]+)/i);
  if (plain?.[1]) return plain[1].trim().replace(/^["']|["']$/g, "");
  return fallback;
}

export async function downloadChatMessageDocx(messageId: string): Promise<void> {
  const id = (messageId || "").trim();
  if (!isPersistedMessageId(id)) {
    throw new ApiError(400, "Wait for the reply to finish before downloading Word.");
  }
  const response = await fetch(`/api/v1/chat/messages/${encodeURIComponent(id)}/docx`, {
    method: "POST",
    credentials: "include",
    cache: "no-store",
  });
  if (!response.ok) {
    let detail: string | null = null;
    try {
      detail = parseErrorPayload(await response.json());
    } catch {
      /* ignore */
    }
    throw new ApiError(response.status, detail || httpErrorFallback(response.status));
  }
  const buffer = new Uint8Array(await response.arrayBuffer());
  const type = (response.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
  if (!buffer.length || buffer[0] !== 0x50 || buffer[1] !== 0x4b) {
    throw new ApiError(502, "Could not download that Word file.");
  }
  if (type && !type.includes("wordprocessingml") && type !== "application/octet-stream") {
    throw new ApiError(502, "Could not download that Word file.");
  }
  const blob = new Blob([buffer], { type: DOCX_TYPE });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filenameFromContentDisposition(response.headers.get("content-disposition"));
  link.rel = "noopener";
  document.body.appendChild(link);
  link.click();
  window.setTimeout(() => {
    URL.revokeObjectURL(objectUrl);
    link.remove();
  }, 60_000);
}
