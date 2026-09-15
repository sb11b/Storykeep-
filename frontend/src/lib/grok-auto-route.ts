export const AUTO_LOW_MAX_CHARS = 400;

const SMALL_TALK_RE =
  /^(?:hi|hello|hey|yo|thanks|thank you|good (?:morning|afternoon|evening|night)|how(?:'s| is| was| were)? (?:it going|your (?:morning|day|evening|night)|you)|what(?:'s| is|s) up)[\s!?.]*$/i;

const SCHOOL_CODE_RE =
  /```|\b(?:python|javascript|typescript|homework|assignment|algorithm|debug|schoolwork|rewrite paper|linked list|dat[- ]?\d+|code)\b|\b(?:function|class)\s+\w+/i;

const ANALYZE_RE = /\banaly[sz]e\b/i;

/** Match backend Auto: school/code or a long analyze turn. Small talk stays low. */
export function pickXhighForAuto(message: string): boolean {
  const text = (message || "").trim();
  if (!text) return false;
  if (text.length < 160 && SMALL_TALK_RE.test(text)) return false;
  if (SCHOOL_CODE_RE.test(text)) return true;
  if (text.length >= AUTO_LOW_MAX_CHARS && ANALYZE_RE.test(text)) return true;
  return false;
}

export function autoReasoningEffort(message: string): "low" | "xhigh" {
  return pickXhighForAuto(message) ? "xhigh" : "low";
}

/** Model · reasoning Auto will POST for this typed line. */
export function autoPostedSpend(message: string): { model: string; reasoning: "low" | "xhigh" } {
  return { model: "grok-4.6", reasoning: autoReasoningEffort(message) };
}

export function postedSpendForTurn(
  modelChoice: string,
  reasoningEffort: string,
  message: string,
): { model: string; reasoning: string } {
  const auto = autoPostedSpend(message);
  if (modelChoice === "auto" || reasoningEffort === "auto") return auto;
  if (reasoningEffort === "xhigh" && auto.reasoning === "low") return auto;
  return { model: "grok-4.6", reasoning: reasoningEffort || "low" };
}
