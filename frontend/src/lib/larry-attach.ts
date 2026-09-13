export const LARRY_ATTACH_ACCEPT = ".pdf,.txt,.md,.docx,.png,.jpg,.jpeg,.gif,.webp,.csv";
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
};

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
