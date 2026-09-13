import { normalizeVisibleSpeechScript, visibleSpeechPlaintext, wrapVisibleSpeechNodes } from "@/lib/tts-visible";

export type GrokReplySpeech = {
  script: string;
  visibleWordCount: number;
  source: "innerText" | "wrappedWords" | "markdown" | "empty";
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
    };
  }

  const fromWords = normalizeVisibleSpeechScript(visibleSpeechPlaintext(root));
  if (fromWords) {
    return {
      script: fromWords,
      visibleWordCount: wrappedCount || (fromWords.match(/\S+/g)?.length ?? 0),
      source: "wrappedWords",
    };
  }

  const fromMarkdown = normalizeVisibleSpeechScript(markdownFallback || "");
  if (fromMarkdown) {
    return {
      script: fromMarkdown,
      visibleWordCount: fromMarkdown.match(/\S+/g)?.length ?? 0,
      source: "markdown",
    };
  }

  return { script: "", visibleWordCount: 0, source: "empty" };
}
