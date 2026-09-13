import { normalizeVisibleSpeechScript } from "@/lib/tts-visible";
import { chatSpeechPlain } from "@/lib/tts-words";

/** The reply row. The Listen button lives inside it, so walk up from the button. */
export const REPLY_ROW_SELECTOR = '[data-role="assistant"], .larry-reply, .chat-message';

/** The rendered markdown body inside a reply row. */
export const REPLY_BODY_SELECTOR = "[data-larry-reply-body], [data-reply-body], .markdown, .prose";

export type ReplyText = {
  text: string;
  chars: number;
  className: string;
  source: "row" | "body" | "markdown" | "empty";
};

function domText(el: HTMLElement | null): string {
  if (!el) return "";
  const inner = (el as HTMLElement & { innerText?: string }).innerText;
  return normalizeVisibleSpeechScript(inner || el.textContent || "");
}

function classNameOf(el: HTMLElement | null): string {
  const name = typeof el?.className === "string" ? el.className.trim() : "";
  return name || "(no class)";
}

/** Reply body for a Listen button: up to the row, then down to the markdown body. */
export function replyBodyFromTrigger(trigger: HTMLElement | null): HTMLElement | null {
  if (typeof trigger?.closest !== "function") return null;
  const row = trigger.closest<HTMLElement>(REPLY_ROW_SELECTOR);
  if (!row) return null;
  return row.querySelector<HTMLElement>(REPLY_BODY_SELECTOR) ?? row;
}

/**
 * Text for Listen, taken from the reply the user is looking at.
 *
 * The button's own row is the starting point, so there is no document-wide
 * lookup to miss. The stored markdown is the last resort, which means a reply
 * with words on screen always has something to speak.
 */
export function readReplyText({
  trigger = null,
  body = null,
  markdown = null,
}: {
  trigger?: HTMLElement | null;
  body?: HTMLElement | null;
  markdown?: string | null;
}): ReplyText {
  const fromTrigger = replyBodyFromTrigger(trigger);
  const candidates: Array<[HTMLElement | null, ReplyText["source"]]> = [
    [fromTrigger, "row"],
    [body, "body"],
  ];
  for (const [el, source] of candidates) {
    const text = domText(el);
    if (text) return { text, chars: text.length, className: classNameOf(el), source };
  }

  const fromMarkdown = normalizeVisibleSpeechScript(chatSpeechPlain(markdown));
  if (fromMarkdown) {
    return {
      text: fromMarkdown,
      chars: fromMarkdown.length,
      className: "(markdown state)",
      source: "markdown",
    };
  }

  return { text: "", chars: 0, className: "(none)", source: "empty" };
}

export function logReplyText(stage: string, resolved: ReplyText) {
  console.log("larry-tts", {
    stage,
    chars: resolved.chars,
    className: resolved.className,
    source: resolved.source,
    sample: resolved.text.slice(0, 80),
  });
}
