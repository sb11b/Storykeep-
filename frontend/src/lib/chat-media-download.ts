const MEDIA_ID = /\/api\/v1\/media\/([0-9a-fA-F-]{36})/;

const TYPE_EXT: Record<string, string> = {
  "image/jpeg": ".jpg",
  "image/jpg": ".jpg",
  "image/png": ".png",
  "image/gif": ".gif",
  "image/webp": ".webp",
  "application/pdf": ".pdf",
};

export class MediaDownloadError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

export function mediaIdFromUrl(url: string | null | undefined): string | null {
  const match = (url || "").match(MEDIA_ID);
  return match?.[1] || null;
}

export function storykeepDownloadFilename(mediaId: string, contentType?: string | null): string {
  const ctype = (contentType || "").split(";")[0].trim().toLowerCase();
  let ext = TYPE_EXT[ctype] || "";
  if (!ext && ctype.startsWith("image/")) ext = ".jpg";
  if (!ext) ext = ".jpg";
  return `storykeep-${mediaId}${ext}`;
}

export function mediaDownloadUrl(mediaId: string): string {
  return `/api/v1/media/${mediaId}?download=1`;
}

function saveBlob(blob: Blob, filename: string) {
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
}

export async function downloadChatPicture(options: {
  mediaId: string;
  url?: string | null;
  contentType?: string | null;
}): Promise<void> {
  const mediaId = (options.mediaId || mediaIdFromUrl(options.url) || "").trim();
  if (!mediaId) {
    throw new MediaDownloadError(400, "Could not download that picture.");
  }
  const href = options.url?.includes("download=1")
    ? options.url
    : mediaDownloadUrl(mediaId);
  const response = await fetch(href, { credentials: "include", cache: "no-store" });
  if (response.status === 401 || response.status === 404) {
    throw new MediaDownloadError(response.status, "Could not download that picture.");
  }
  if (!response.ok) {
    throw new MediaDownloadError(response.status, "Could not download that picture.");
  }
  const blob = await response.blob();
  const type = (blob.type || response.headers.get("content-type") || "").toLowerCase();
  if (type.includes("text/html") || type.includes("application/json")) {
    throw new MediaDownloadError(502, "Could not download that picture.");
  }
  const filename = storykeepDownloadFilename(mediaId, options.contentType || blob.type);
  saveBlob(blob, filename);
}
