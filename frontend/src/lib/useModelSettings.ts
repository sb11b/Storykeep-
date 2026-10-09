"use client";

import { api } from "@/lib/api";

type ModelPane = {
  conversationId: string | null;
  modelChoice: string;
  reasoningEffort: string;
  lastResolvedModel: string | null;
  lastResolvedReasoning: string | null;
};

type ModelPatch = {
  modelChoice?: string;
  reasoningEffort?: string;
  lastResolvedModel?: string | null;
  lastResolvedReasoning?: string | null;
  recapQuestion?: boolean;
};

type UseModelSettingsOptions = {
  pane: ModelPane;
  persist: boolean;
  patch: (partial: ModelPatch) => void;
  isGrokReasoningEffort: (value: string | null | undefined) => value is string;
  onHistoryChanged?: () => void;
};

export function useModelSettings({
  pane,
  persist,
  patch,
  isGrokReasoningEffort,
  onHistoryChanged,
}: UseModelSettingsOptions) {
  async function setModelChoice(next: string) {
    const reasoning = next === "auto" ? "auto" : pane.reasoningEffort === "auto" ? "low" : pane.reasoningEffort;
    patch({ modelChoice: next, reasoningEffort: next === "auto" ? pane.reasoningEffort : reasoning });
    if (!pane.conversationId || !persist) return;
    try {
      const updated = await api.patchChatConversation(pane.conversationId, {
        model: next,
        reasoning: next === "auto" ? "auto" : reasoning,
      });
      patch({
        modelChoice: updated.model,
        lastResolvedModel: updated.last_model ?? pane.lastResolvedModel,
        reasoningEffort:
          updated.model === "auto"
            ? pane.reasoningEffort
            : isGrokReasoningEffort(updated.reasoning)
              ? updated.reasoning
              : reasoning,
        lastResolvedReasoning: updated.last_reasoning ?? pane.lastResolvedReasoning,
      });
      onHistoryChanged?.();
    } catch {
      /* ignore */
    }
  }

  async function setReasoningEffort(next: string) {
    patch({ reasoningEffort: next });
    if (pane.modelChoice === "auto" || !pane.conversationId || !persist) return;
    try {
      const updated = await api.patchChatConversation(pane.conversationId, { reasoning: next });
      patch({
        reasoningEffort: isGrokReasoningEffort(updated.reasoning) ? updated.reasoning : next,
        lastResolvedReasoning: updated.last_reasoning ?? pane.lastResolvedReasoning,
      });
      onHistoryChanged?.();
    } catch {
      /* ignore */
    }
  }

  async function setRecapQuestion(next: boolean) {
    patch({ recapQuestion: next });
    if (!pane.conversationId || !persist) return;
    try {
      await api.patchChatConversation(pane.conversationId, { recap_question: next });
    } catch {
      /* ignore */
    }
  }

  return { setModelChoice, setReasoningEffort, setRecapQuestion };
}
