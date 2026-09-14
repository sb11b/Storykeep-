export const GROK_REASONING_EFFORTS = ["low", "medium", "high", "xhigh"] as const;

export type GrokReasoningEffort = (typeof GROK_REASONING_EFFORTS)[number];

export function shortGrokModelName(model?: string | null): string {
  const id = (model || "").trim();
  if (!id) return "4.6";
  return id.replace(/^grok-/i, "");
}

/** Auto choice shown on the reply, e.g. "Auto → 4.6 · low". */
export function autoRouteLabel(
  choice: string,
  model?: string | null,
  reasoning?: string | null,
): string | null {
  if (choice !== "auto") return null;
  if (!model && !reasoning) return null;
  const short = shortGrokModelName(model || "grok-4.6");
  if (reasoning) return `Auto → ${short} · ${reasoning}`;
  return `Auto → ${short}`;
}

/** Per-turn spend chip. Always includes model and reasoning (never silent on xhigh). */
export function spendChipLabel(model?: string | null, reasoning?: string | null): string {
  const resolvedModel = (model || "").trim() || "grok-4.6";
  const resolvedReasoning = (reasoning || "").trim() || "low";
  return `this turn · ${resolvedModel} · ${resolvedReasoning}`;
}

export function grokModelLabel(
  choice: string,
  lastModel?: string | null,
  lastReasoning?: string | null,
): string {
  if (choice === "auto") {
    return autoRouteLabel("auto", lastModel, lastReasoning) || "Auto";
  }
  if (lastReasoning) return `${choice} · ${lastReasoning}`;
  return choice;
}

export function isGrokReasoningEffort(value: string | null | undefined): value is GrokReasoningEffort {
  return Boolean(value && GROK_REASONING_EFFORTS.includes(value as GrokReasoningEffort));
}
