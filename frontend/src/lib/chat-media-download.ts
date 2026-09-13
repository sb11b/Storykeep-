const MEDIA_ID = /\/api\/v1\/media\/([0-9a-fA-F-]{36})/;

const TYPE_EXT: Record<string, string> = {
  "image/jpeg": ".jpg",
  "image/jpg": ".jpg",
  "image/png": ".png",
  "image/gif": ".gif",
  "image/webp": ".webp",
};

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

/** Same path as the <img> src so the session cookie is sent. */
export function mediaDownloadUrl(mediaId: string): string {
  return `/api/v1/media/${mediaId}`;
}
