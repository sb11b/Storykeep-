export const GROK_REASONING_EFFORTS = ["low", "medium", "high", "xhigh"] as const;

export type GrokReasoningEffort = (typeof GROK_REASONING_EFFORTS)[number];

export function grokModelLabel(
  choice: string,
  lastModel?: string | null,
  lastReasoning?: string | null,
): string {
  if (choice === "auto") {
    if (lastModel && lastReasoning) return `Auto · ${lastModel} · ${lastReasoning}`;
    if (lastModel) return `Auto · ${lastModel}`;
    return "Auto";
  }
  if (lastReasoning) return `${choice} · ${lastReasoning}`;
  return choice;
}

export function isGrokReasoningEffort(value: string | null | undefined): value is GrokReasoningEffort {
  return Boolean(value && GROK_REASONING_EFFORTS.includes(value as GrokReasoningEffort));
}
