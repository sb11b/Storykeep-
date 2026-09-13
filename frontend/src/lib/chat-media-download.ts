const MEDIA_ID = /\/api\/v1\/media\/([0-9a-fA-F-]{36})/;
const UUID = /^[0-9a-fA-F-]{36}$/;
const ACCIDENTAL_EXT = /(\/api\/v1\/media\/[0-9a-fA-F-]{36})\.(jpg|jpeg|png|gif|webp)(?=(\?|$))/i;

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

export function mediaDownloadUrl(mediaId: string): string {
  return `/api/v1/media/${mediaId}`;
}

function stripAccidentalPathExt(src: string): string {
  if (src.startsWith("blob:") || src.startsWith("data:")) return src;
  return src.replace(ACCIDENTAL_EXT, "$1");
}

/**
 * Exact GET URL for Download. Must match the working <img> src (origin, path, query, UUID).
 * Never append .jpg to the request path. Never replace a live src with a reconstructed /media/{id}.
 */
export function resolveChatImageSrc(
  imgSrc: string | null | undefined,
  mediaId?: string | null,
): string {
  const raw = (imgSrc || "").trim();
  if (raw) return stripAccidentalPathExt(raw);
  const id = (mediaId || "").trim();
  if (UUID.test(id)) return mediaDownloadUrl(id);
  return "";
}

export function liveChatImageSrc(
  img?: Pick<HTMLImageElement, "getAttribute" | "currentSrc"> | null,
  fallbackUrl?: string | null,
): string {
  const attr = img?.getAttribute?.("src")?.trim() || "";
  const current = (img?.currentSrc || "").trim();
  return current || attr || (fallbackUrl || "").trim();
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
  img?: Pick<HTMLImageElement, "getAttribute" | "currentSrc"> | null;
  mediaId?: string | null;
  url?: string | null;
  contentType?: string | null;
}): Promise<void> {
  const imgSrc = liveChatImageSrc(options.img, options.url);
  const downloadUrl = resolveChatImageSrc(imgSrc);
  const mediaId = mediaIdFromUrl(downloadUrl) || mediaIdFromUrl(imgSrc) || (options.mediaId || "").trim();
  if (process.env.NODE_ENV !== "production") {
    console.info("[storykeep-download]", { imgSrc: imgSrc || null, downloadUrl: downloadUrl || null });
  }
  if (!downloadUrl) {
    throw new MediaDownloadError(400, "Could not download that picture. (HTTP 400)");
  }
  const response = await fetch(downloadUrl, {
    method: "GET",
    credentials: "include",
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
  const blob = new Blob([buffer], { type: sniffed });
  const objectUrl = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = objectUrl;
  link.download = storykeepDownloadFilename(mediaId || "image", options.contentType || sniffed);
  link.rel = "noopener";
  link.setAttribute("aria-label", "Download picture");
  document.body.appendChild(link);
  link.click();
  window.setTimeout(() => {
    URL.revokeObjectURL(objectUrl);
    link.remove();
  }, REVOKE_MS);
}
