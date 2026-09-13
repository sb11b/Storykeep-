const MEDIA_ID = /\/api\/v1\/media\/([0-9a-fA-F-]{36})/;

const TYPE_EXT: Record<string, string> = {
  "image/jpeg": ".jpg",
  "image/jpg": ".jpg",
  "image/png": ".png",
  "image/gif": ".gif",
  "image/webp": ".webp",
};

const REVOKE_MS = 60_000;

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

/** Same path as the <img> src. */
export function mediaDownloadUrl(mediaId: string): string {
  return `/api/v1/media/${mediaId}`;
}

export function sniffImageContentType(bytes: Uint8Array): string | null {
  if (bytes.length >= 2 && bytes[0] === 0xff && bytes[1] === 0xd8) return "image/jpeg";
  if (bytes.length >= 8 && bytes[0] === 0x89 && bytes[1] === 0x50 && bytes[2] === 0x4e && bytes[3] === 0x47) {
    return "image/png";
  }
  if (bytes.length >= 6) {
    const gif = String.fromCharCode(bytes[0]!, bytes[1]!, bytes[2]!, bytes[3]!, bytes[4]!, bytes[5]!);
    if (gif === "GIF87a" || gif === "GIF89a") return "image/gif";
  }
  if (bytes.length >= 12) {
    const riff = String.fromCharCode(bytes[0]!, bytes[1]!, bytes[2]!, bytes[3]!);
    const webp = String.fromCharCode(bytes[8]!, bytes[9]!, bytes[10]!, bytes[11]!);
    if (riff === "RIFF" && webp === "WEBP") return "image/webp";
  }
  return null;
}

function looksLikeHtmlOrJson(bytes: Uint8Array, contentType: string): boolean {
  if (contentType.includes("text/html") || contentType.includes("application/json")) return true;
  const start = String.fromCharCode(...bytes.slice(0, 16)).trimStart().toLowerCase();
  return start.startsWith("<!doctype") || start.startsWith("<html") || start.startsWith("{") || start.startsWith("[");
}

export async function downloadChatPicture(options: {
  mediaId: string;
  url?: string | null;
  contentType?: string | null;
}): Promise<void> {
  const mediaId = (options.mediaId || mediaIdFromUrl(options.url) || "").trim();
  if (!/^[0-9a-fA-F-]{36}$/.test(mediaId)) {
    throw new MediaDownloadError(400, "Could not download that picture. (HTTP 400)");
  }
  const href = mediaDownloadUrl(mediaId);
  const response = await fetch(href, {
    method: "GET",
    credentials: "include",
    cache: "no-store",
    mode: "same-origin",
    headers: { Accept: "image/jpeg,image/png,image/webp,image/gif,image/*" },
  });
  if (!response.ok) {
    throw new MediaDownloadError(
      response.status,
      `Could not download that picture. (HTTP ${response.status})`,
    );
  }
  const buffer = new Uint8Array(await response.arrayBuffer());
  const headerType = (response.headers.get("content-type") || "").split(";")[0].trim().toLowerCase();
  const sniffed = sniffImageContentType(buffer);
  if (!sniffed || looksLikeHtmlOrJson(buffer, headerType)) {
    throw new MediaDownloadError(response.status, `Could not download that picture. (HTTP ${response.status})`);
  }
  const type = sniffed;
  const blob = new Blob([buffer], { type });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = storykeepDownloadFilename(mediaId, options.contentType || type);
  link.rel = "noopener";
  link.setAttribute("aria-label", "Download picture");
  document.body.appendChild(link);
  link.click();
  window.setTimeout(() => {
    URL.revokeObjectURL(objectUrl);
    link.remove();
  }, REVOKE_MS);
}
