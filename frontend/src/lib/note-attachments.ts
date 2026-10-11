// Media links in note markdown are written relative in dev and absolute in
// packaged builds, so the origin prefix is optional when parsing either.
const ORIGIN_PREFIX = "(?:[A-Za-z][A-Za-z0-9+.-]*://[^)\\s]*)?";
const MEDIA_PATH = "/api/v1/media";

const MEDIA_REF = new RegExp(
  `(!)?\\[([^\\]]*)\\]\\((${ORIGIN_PREFIX}${MEDIA_PATH}/([0-9a-fA-F-]{36}))\\)`,
  "g",
);

export type NoteAttachment = {
  id: string;
  label: string;
  url: string;
  isImage: boolean;
};

export function parseNoteAttachments(markdown: string): NoteAttachment[] {
  const seen = new Set<string>();
  const items: NoteAttachment[] = [];
  for (const match of markdown.matchAll(MEDIA_REF)) {
    const id = match[4];
    if (!id || seen.has(id)) continue;
    seen.add(id);
    items.push({
      id,
      label: (match[2] || "attachment").trim(),
      url: match[3],
      isImage: Boolean(match[1]),
    });
  }
  return items;
}

export function fileAttachments(markdown: string): NoteAttachment[] {
  return parseNoteAttachments(markdown).filter((item) => !item.isImage);
}

export function removeAttachmentFromMarkdown(markdown: string, mediaId: string): string {
  // Matches both the dev-relative and the packaged-absolute media URL, since
  // the token is a suffix of either.
  const token = `${MEDIA_PATH}/${mediaId}`;
  const lines = markdown.split("\n").filter((line) => !line.includes(token));
  let next = lines.join("\n");
  const escaped = mediaId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  next = next.replace(new RegExp(`!\\[[^\\]]*\\]\\(${ORIGIN_PREFIX}${MEDIA_PATH}/${escaped}\\)`, "g"), "");
  next = next.replace(new RegExp(`\\[[^\\]]*\\]\\(${ORIGIN_PREFIX}${MEDIA_PATH}/${escaped}\\)`, "g"), "");
  return next.replace(/\n{3,}/g, "\n\n").trimEnd();
}
