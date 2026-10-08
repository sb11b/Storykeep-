"use client";

import { toast } from "sonner";
import { api } from "@/lib/api";

type SnippetMessage = {
  id: string;
  role: string;
  content: string;
  routeLabel?: string | null;
};

type SnippetPane = {
  lastResolvedModel: string | null;
  conversationId: string | null;
  messages: SnippetMessage[];
};

type UseSnippetRunnerOptions<T extends SnippetPane> = {
  onUpdate: (updater: (current: T) => T) => void;
  onHistoryChanged?: () => void;
  setBusy: (busy: boolean) => void;
  spendChipLabel: (model?: string | null, reasoning?: string | null) => string;
};

export function useSnippetRunner<T extends SnippetPane>({
  onUpdate,
  onHistoryChanged,
  setBusy,
  spendChipLabel,
}: UseSnippetRunnerOptions<T>) {
  async function runSnippet(messageId: string, code: string) {
    const snippet = code.trim();
    if (!snippet) {
      toast.error("That code fence is empty.");
      return;
    }
    setBusy(true);
    try {
      const result = await api.runChatSnippet(messageId, snippet);
      onUpdate((current) => {
        const extra: T["messages"] = [
          { id: result.user_message.id, role: "user", content: result.user_message.content || "" },
          {
            id: result.assistant_message.id,
            role: "assistant",
            content: result.assistant_message.content || "",
            routeLabel: spendChipLabel(current.lastResolvedModel, "low"),
          },
        ] as T["messages"];
        const merged = [...current.messages];
        for (const line of extra) {
          if (!merged.some((row) => row.id === line.id)) merged.push(line);
        }
        return { ...current, conversationId: result.conversation_id || current.conversationId, messages: merged };
      });
      onHistoryChanged?.();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : "Could not run that snippet.");
    } finally {
      setBusy(false);
    }
  }

  return { runSnippet };
}
