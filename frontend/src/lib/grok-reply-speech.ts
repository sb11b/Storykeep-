import { normalizeVisibleSpeechScript, visibleSpeechPlaintext, wrapVisibleSpeechNodes } from "@/lib/tts-visible";

/** The assistant markdown body Listen reads from. */
export const GROK_REPLY_SELECTOR = "div.note-md[data-grok-reply-body]";

/** Selector for one rendered reply body, by message id. */
export function replyBodySelector(messageId: string): string {
  return `div.note-md[data-grok-reply-body="${messageId}"]`;
}

export type RenderedReplyText = { text: string; selector: string; found: boolean };

/**
 * Read the reply the user is looking at, straight off the document.
 *
 * `innerText` is what is on screen, so this is the only source of truth for
 * whether there is anything to speak.
 */
export function readRenderedReplyText(messageId: string): RenderedReplyText {
  const selector = replyBodySelector(messageId);
  const el = typeof document === "undefined" ? null : document.querySelector<HTMLElement>(selector);
  const text = (el?.innerText ?? "").trim();
  console.log("larry-tts", text.length, text.slice(0, 80));
  return { text, selector, found: Boolean(el) };
}

export type GrokReplySpeech = {
  script: string;
  visibleWordCount: number;
  source: "innerText" | "wrappedWords" | "markdown" | "empty";
  selector: string;
};

function elementText(root: HTMLElement | null): string {
  if (!root) return "";
  const inner = (root as HTMLElement & { innerText?: string }).innerText;
  return normalizeVisibleSpeechScript(inner || root.textContent || "");
}

/**
 * Speech string for a Grok reply.
 *
 * innerText of the rendered markdown body is authoritative: if the user can see
 * words, TTS gets them. Word spans are still wrapped so the highlight cue can
 * follow along, and the raw markdown is a last resort when the body is unmounted.
 */
export function grokReplySpeechScript(
  root: HTMLElement | null,
  markdownFallback?: string | null,
): GrokReplySpeech {
  const selector = root ? GROK_REPLY_SELECTOR : "(markdown state)";
  let wrappedCount = 0;
  if (root) {
    try {
      wrappedCount = wrapVisibleSpeechNodes(root);
    } catch {
      wrappedCount = 0;
    }
  }

  const fromInnerText = elementText(root);
  if (fromInnerText) {
    return {
      script: fromInnerText,
      visibleWordCount: wrappedCount || (fromInnerText.match(/\S+/g)?.length ?? 0),
      source: "innerText",
      selector,
    };
  }

  const fromWords = normalizeVisibleSpeechScript(visibleSpeechPlaintext(root));
  if (fromWords) {
    return {
      script: fromWords,
      visibleWordCount: wrappedCount || (fromWords.match(/\S+/g)?.length ?? 0),
      source: "wrappedWords",
      selector,
    };
  }

  const fromMarkdown = normalizeVisibleSpeechScript(markdownFallback || "");
  if (fromMarkdown) {
    return {
      script: fromMarkdown,
      visibleWordCount: fromMarkdown.match(/\S+/g)?.length ?? 0,
      source: "markdown",
      selector: "(markdown state)",
    };
  }

  return { script: "", visibleWordCount: 0, source: "empty", selector };
}
