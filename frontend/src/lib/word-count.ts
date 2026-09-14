/** Visible word count, ignoring ==highlight== / <mark> wrappers. */
export function stripMarks(text: string | null | undefined): string {
  return (text || "")
    .replace(/==([^=]+)==/g, "$1")
    .replace(/<\/?mark>/gi, "");
}

export function wordCount(text: string | null | undefined): number {
  const cleaned = stripMarks(text).trim();
  if (!cleaned) return 0;
  return cleaned.split(/\s+/).filter(Boolean).length;
}

export function hasGrammarMarks(text: string | null | undefined): boolean {
  return /==[^=]+==|<mark[\s>]/i.test(text || "");
}
