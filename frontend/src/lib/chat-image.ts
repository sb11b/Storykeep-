/** Junior chat image-edit/generate intent. Keep in sync with backend chat_image.py. */

const VISION_ONLY = [
  /\bwhat(?:'s| is) in (?:this|the|my) (?:photo|picture|image|pic|selfie)\b/i,
  /\bwhat(?:'s| is) (?:this|that) (?:photo|picture|image|pic|selfie)\b/i,
  /\bwhat (?:do you |can you )?see\b/i,
  /\bdescribe (?:this|the|my) (?:photo|picture|image|pic|selfie)\b/i,
  /\blook at (?:this|the|my) (?:photo|picture|image|pic|selfie)\b/i,
  /\bhow old\b/i,
  /^please look at /i,
];

const EDIT = [
  /\blook older\b/i,
  /\bmake (?:me|it|this|that|him|her|them) look\b/i,
  /\bmake (?:me|it|this|that) older\b/i,
  /\bolder version\b/i,
  /\bage (?:this|the|me|my)\b/i,
  /\bage(?:ing)? (?:this|the|my) (?:photo|picture|image|pic|selfie)\b/i,
  /\b(?:older|age) (?:this|the|my) (?:photo|picture|image|pic|selfie)\b/i,
  /\bedit (?:this|the|my) (?:photo|picture|image|pic|selfie)\b/i,
  /\bmake (?:this|the|my) (?:photo|picture|image|pic|selfie)\b/i,
  /\bturn (?:this|the|my) (?:photo|picture|image|pic|selfie)\b/i,
  /\bchange (?:this|the|my) (?:photo|picture|image|pic|selfie)\b/i,
  /\bretouch\b/i,
  /\bfrom this (?:photo|picture|image|pic|selfie)\b/i,
  /\bbased on (?:this|the|my) (?:attached )?(?:photo|picture|image|pic|selfie)\b/i,
];

const GENERATE = [
  /\bgenerate (?:an? )?(?:image|photo|picture|portrait|drawing)\b/i,
  /\bgenerate (?:me )?(?:an? |the |this )/i,
  /\bcreate (?:an? )?(?:image|photo|picture|portrait)\b/i,
  /\bdraw (?:me |an? |this |a )/i,
  /\bmake (?:an? )?(?:image|photo|picture|portrait) of\b/i,
  /\bimagine (?:an? )?(?:image|photo|picture|portrait)\b/i,
  /\brecreat(?:e|ing) (?:an? |this |the |my )?(?:image|photo|picture|pic|selfie|portrait)/i,
];

const AGE = [
  /\bolder\b/i,
  /\bage(?:ing)?\b/i,
  /\bgray(?:er)?\b/i,
  /\bgrey(?:er)?\b/i,
  /\bwrinkl/i,
  /\btemples\b/i,
];

const CODE_GENERATE = /\b(?:linked list|homework|algorithm|typescript|javascript|function|class)\b/i;
const IMAGE_NOUN = /\b(?:image|photo|picture|portrait|drawing|selfie)\b/i;
const QUOTE = /["“”]([^"“”]{0,240})["“”]/g;
const TICK = /`([^`]{0,240})`/g;
const TALK = [
  /\bwhat should i\b/i,
  /\bwhat do i (?:get|expect|see)\b/i,
  /\bexpect from\b/i,
  /\bchat reliability\b/i,
  /\btell me (?:what|about)\b/i,
  /\bexplain\b/i,
  /\bimage[- ]gate\b/i,
  /\bimage path\b/i,
  /\bspec quotes?\b/i,
  /\bpasted ticket\b/i,
  /\bverify:/i,
  /^verify\b/i,
  /^bug\b/i,
  /^fix\b/i,
];
const COMMAND_START =
  /^(?:please |can you |could you )?(?:generate|draw|create (?:an? )?(?:image|photo|picture|portrait)|make (?:an? )?(?:image|photo|picture|portrait) of|make (?:me|it|this|that|him|her|them) (?:look )?(?:older|younger)|make (?:me|it|this|that|him|her|them) look|age (?:this|the|me|my)|edit (?:this|the|my) (?:photo|picture|image|pic|selfie)|recreate (?:an? |this |the |my )?(?:image|photo|picture|pic|selfie|portrait))/i;

function commandText(text: string): string {
  const leftover = text.replace(QUOTE, " ").replace(TICK, " ").replace(/\s+/g, " ").trim();
  if (leftover.length >= 12) return leftover;
  return text.replace(/\s+/g, " ").trim();
}

function isTalkTurn(text: string): boolean {
  if (TALK.some((pattern) => pattern.test(text))) return true;
  const lines = text.split(/\n/).map((line) => line.trim()).filter(Boolean);
  if (
    lines.length >= 4 &&
    lines.some((line) => /^(bug|fix|verify|-|\*|1\.|2\.)/i.test(line))
  ) {
    return true;
  }
  return false;
}

function isPrimaryImageCommand(text: string): boolean {
  const compact = text.replace(/\s+/g, " ").trim();
  if (!compact) return false;
  if (COMMAND_START.test(compact)) return true;
  return compact.length <= 140;
}

export type ImageToolIntent = "edit" | "generate" | "clarify";

export function imageToolIntent(text: string, hasImage: boolean): ImageToolIntent | null {
  const raw = (text || "").trim();
  if (!raw) return null;
  if (isTalkTurn(raw)) return null;
  const command = commandText(raw);
  if (isTalkTurn(command)) return null;
  if (!isPrimaryImageCommand(command)) return null;
  if (VISION_ONLY.some((pattern) => pattern.test(command))) return null;
  if (GENERATE.some((pattern) => pattern.test(command))) {
    if (hasImage) return "edit";
    if (CODE_GENERATE.test(command) && !IMAGE_NOUN.test(command)) return null;
    return "generate";
  }
  if (EDIT.some((pattern) => pattern.test(command))) return hasImage ? "edit" : "clarify";
  if (hasImage && command.length <= 48 && AGE.some((pattern) => pattern.test(command))) return "edit";
  return null;
}

export function collectImageMediaIds(
  pending: { id: string; kind?: string }[] | null | undefined,
  messages: { role?: string; files?: { kind?: string; media_id?: string }[] | null }[] | null | undefined,
): string[] {
  const fromPending = (pending || []).filter((item) => item.kind === "image" && item.id).map((item) => item.id);
  if (fromPending.length) return fromPending;
  for (let index = (messages || []).length - 1; index >= 0; index -= 1) {
    const row = messages![index];
    if (row.role !== "user") continue;
    const ids = (row.files || [])
      .filter((item) => item.kind === "image" && item.media_id)
      .map((item) => item.media_id!) ;
    if (ids.length) return ids;
  }
  return [];
}

export const CLARIFY_EDIT_OR_GENERATE =
  "Generate a new older-looking picture, or attach one to edit?";

export const MISSING_PHOTO_DETAIL = CLARIFY_EDIT_OR_GENERATE;

export const MEDIA_MARKDOWN = /!\[[^\]]*\]\(\/api\/v1\/media\/[0-9a-fA-F-]{36}\)/;
