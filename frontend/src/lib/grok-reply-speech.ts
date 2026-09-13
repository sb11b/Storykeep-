import { normalizeVisibleSpeechScript, visibleSpeechPlaintext, wrapVisibleSpeechNodes } from "@/lib/tts-visible";

/** The assistant markdown body Listen reads from. */
export const GROK_REPLY_SELECTOR = "div.note-md[data-grok-reply-body]";

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

/**
 * Resolve reply text for Listen, retrying once after a frame so a reply that is
 * still painting does not read as empty.
 */
export async function resolveGrokReplyText(
  root: HTMLElement | null,
  markdownFallback?: string | null,
): Promise<GrokReplySpeech> {
  let payload = grokReplySpeechScript(root, markdownFallback);
  if (!payload.script && typeof requestAnimationFrame === "function") {
    await new Promise<void>((resolve) => requestAnimationFrame(() => resolve()));
    payload = grokReplySpeechScript(root, markdownFallback);
  }
  console.info("[grok-tts] reply text", {
    chars: payload.script.length,
    selector: payload.selector,
    source: payload.source,
  });
  return payload;
}
