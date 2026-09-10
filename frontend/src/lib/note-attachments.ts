const MEDIA_REF =
  /(!)?\[([^\]]*)\]\((\/api\/v1\/media\/([0-9a-fA-F-]{36}))\)/g;

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
  const token = `/api/v1/media/${mediaId}`;
  const lines = markdown.split("\n").filter((line) => !line.includes(token));
  let next = lines.join("\n");
  const escaped = mediaId.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  next = next.replace(new RegExp(`!\\[[^\\]]*\\]\\(/api/v1/media/${escaped}\\)`, "g"), "");
  next = next.replace(new RegExp(`\\[[^\\]]*\\]\\(/api/v1/media/${escaped}\\)`, "g"), "");
  return next.replace(/\n{3,}/g, "\n\n").trimEnd();
}
