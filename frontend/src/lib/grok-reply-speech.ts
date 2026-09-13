import { buildVisibleSpeechScript, normalizeVisibleSpeechScript } from "@/lib/tts-visible";

/** Plaintext for Grok reply TTS — prefers visible DOM, falls back to markdown source. */
export function grokReplySpeechScript(
  root: HTMLElement | null,
  markdownFallback?: string | null,
): { script: string; visibleWordCount: number } {
  const wrapped = buildVisibleSpeechScript(root);
  let script = wrapped.script.trim();
  if (!script && root) {
    script = normalizeVisibleSpeechScript(root.innerText || root.textContent || "");
  }
  if (!script && markdownFallback?.trim()) {
    script = normalizeVisibleSpeechScript(markdownFallback);
  }
  const visibleWordCount =
    wrapped.visibleWordCount || (script.match(/\S+/g)?.length ?? 0);
  return { script, visibleWordCount };
}
