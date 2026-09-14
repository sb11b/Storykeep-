import { ApiError } from "@/lib/api";
import { httpErrorFallback, parseErrorPayload } from "@/lib/api-errors";

export const LARRY_ATTACH_ACCEPT = ".pdf,.txt,.md,.docx,.png,.jpg,.jpeg,.gif,.webp,.csv";
export const LARRY_IMAGE_ACCEPT =
  "image/png,image/jpeg,image/gif,image/webp,.png,.jpg,.jpeg,.gif,.webp";
export const LARRY_ATTACH_MAX_BYTES = 10 * 1024 * 1024;
export const LARRY_ATTACH_MAX_FILES = 5;

const ALLOWED_SUFFIXES = new Set([".pdf", ".txt", ".md", ".docx", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".csv"]);

export type LarryAttachment = {
  media_id: string;
  filename: string;
  content_type: string;
  kind: "image" | "file";
  url: string;
  byte_size?: number | null;
  extract_text?: string | null;
};

/** Chip shown above the Junior composer before Send. */
export type PendingAttachment = {
  id: string;
  name: string;
  size: number;
  url: string;
  kind: "image" | "file";
  content_type: string;
  extract_text?: string | null;
};

/** Copy a live FileList before the input is reset — resetting empties the list in Chrome. */
export function snapshotFiles(list: FileList | File[] | null | undefined): File[] {
  return Array.from(list ?? []);
}

export function formatFileSize(bytes: number | null | undefined): string {
  const size = Number(bytes) || 0;
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) {
    const kb = size / 1024;
    return `${kb < 10 ? kb.toFixed(1) : Math.round(kb)} KB`;
  }
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

export function suffixOf(filename: string): string {
  const name = filename.replace(/\\/g, "/");
  const dot = name.lastIndexOf(".");
  return dot >= 0 ? name.slice(dot).toLowerCase() : "";
}

export function isAllowedLarryFile(file: File): boolean {
  const suffix = suffixOf(file.name);
  if (suffix === ".jpeg") return true;
  return ALLOWED_SUFFIXES.has(suffix);
}

export function rejectLarryFile(file: File): string | null {
  const suffix = suffixOf(file.name);
  if (suffix === ".doc") {
    return `${file.name} is a legacy .doc file. Save as .docx and attach again.`;
  }
  if (!isAllowedLarryFile(file)) {
    return `${file.name} is not a PDF, TXT, MD, DOCX, CSV, PNG, JPG, GIF, or WebP.`;
  }
  if (file.size > LARRY_ATTACH_MAX_BYTES) {
    return `${file.name} is larger than 10 MB.`;
  }
  return null;
}

export function attachmentMarkdown(files: LarryAttachment[]): string {
  return files
    .map((item) =>
      item.kind === "image"
        ? `![${item.filename.replace(/\.[^.]+$/, "")}](${item.url || `/api/v1/media/${item.media_id}`})`
        : `[${item.filename}](${item.url || `/api/v1/media/${item.media_id}`})`,
    )
    .join("\n");
}

export function pendingToMessageFile(item: PendingAttachment): LarryAttachment {
  return {
    media_id: item.id,
    filename: item.name,
    content_type: item.content_type,
    kind: item.kind,
    url: item.url || `/api/v1/media/${item.id}`,
    byte_size: item.size,
    extract_text: item.extract_text || null,
  };
}

/** POST /api/v1/media with the cookie session. Logs {status, id, name}. */
export async function uploadLarryAttachment(file: File): Promise<PendingAttachment> {
  const body = new FormData();
  body.append("file", file);
  let status = 0;
  try {
    const response = await fetch("/api/v1/media", {
      method: "POST",
      body,
      credentials: "include",
      cache: "no-store",
    });
    status = response.status;
    if (!response.ok) {
      let detail: string | null = null;
      try {
        detail = parseErrorPayload(await response.json());
      } catch {
        /* ignore */
      }
      console.log("larry-attach", { status, id: null, name: file.name });
      throw new ApiError(status, detail || httpErrorFallback(status));
    }
    const uploaded = (await response.json()) as {
      id?: string;
      filename?: string;
      url?: string;
      kind?: "image" | "file";
      byte_size?: number | null;
      extract_text?: string | null;
    };
    const id = uploaded.id || "";
    const name = uploaded.filename || file.name;
    console.log("larry-attach", { status, id, name });
    if (!id) {
      throw new ApiError(status, "Upload succeeded but returned no media id.");
    }
    return {
      id,
      name,
      size: uploaded.byte_size ?? file.size,
      url: uploaded.url || `/api/v1/media/${id}`,
      kind: uploaded.kind === "image" ? "image" : "file",
      content_type: file.type || "application/octet-stream",
      extract_text: uploaded.extract_text || null,
    };
  } catch (error) {
    if (!(error instanceof ApiError)) {
      console.log("larry-attach", { status: status || "network", id: null, name: file.name });
    }
    throw error;
  }
}
