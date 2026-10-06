"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import {
  createGrokPane,
  type GrokPaneState,
} from "@/components/grok-pane";
import { api, ApiError } from "@/lib/api";
import { isConversationId, INVALID_CHAT_TOAST } from "@/lib/chat-conversation";
import { grokModelLabel, isGrokReasoningEffort, spendChipLabel } from "@/lib/grok-model";
import {
  labelsFromPanes,
  loadSavedGrokPanes,
  mergePreferenceLabels,
  saveGrokPanes,
  scrubDefaultPaneLabels,
} from "@/lib/grok-pane-storage";
import { parseCustomNoteShelves, type CustomNoteShelf } from "@/lib/custom-note-shelves";
import { toastActionError } from "@/lib/toast-message";
import { CRYPTO_UNLOCKED, decryptStoredMessage } from "@/lib/message-crypto";
import type { GrokConversation, MessageCryptoStatus } from "@/lib/types";

export const MAX_PANES = 4;

const INITIAL_PANES = loadSavedGrokPanes() ?? [createGrokPane(0)];
const INITIAL_FOCUSED_PANE_ID = INITIAL_PANES[0]!.id;

export function useGrokPanels(persist: boolean, setCustomShelves: (shelves: CustomNoteShelf[]) => void) {
  const [panes, setPanes] = useState<GrokPaneState[]>(INITIAL_PANES);
  const [focusedPaneId, setFocusedPaneId] = useState<string>(INITIAL_FOCUSED_PANE_ID);
  const focusedPaneIdRef = useRef(focusedPaneId);
  const panesRef = useRef(panes);
  panesRef.current = panes;
  const paneLabelsLoadedRef = useRef(false);

  useEffect(() => {
    focusedPaneIdRef.current = focusedPaneId;
  }, [focusedPaneId]);

  useEffect(() => {
    if (paneLabelsLoadedRef.current) return;
    paneLabelsLoadedRef.current = true;
    void api
      .getPreferences()
      .then((prefs) => {
        setCustomShelves(parseCustomNoteShelves(prefs));
        const labels = prefs.grok_pane_labels as Record<string, string> | undefined;
        if (!labels || !Object.keys(labels).length) return;
        setPanes((current) => {
          const merged = mergePreferenceLabels(current, labels);
          saveGrokPanes(merged);
          return merged;
        });
      })
      .catch(() => {
        /* ignore */
      });
  }, []);

  useEffect(() => {
    if (!panes.some((pane) => pane.id === focusedPaneId)) {
      setFocusedPaneId(panes[0]?.id ?? focusedPaneId);
    }
  }, [focusedPaneId, panes]);

  const persistPaneLabels = useCallback(
    async (nextPanes: GrokPaneState[]) => {
      saveGrokPanes(nextPanes);
      try {
        const prefs = await api.getPreferences();
        const existing = scrubDefaultPaneLabels(prefs.grok_pane_labels as Record<string, string> | undefined);
        const merged = scrubDefaultPaneLabels({ ...existing, ...labelsFromPanes(nextPanes) });
        await api.updatePreferences({ grok_pane_labels: merged });
      } catch (error) {
        toastActionError(error, "save pane name", "Could not save that pane name");
      }
    },
    [],
  );

  const addPane = useCallback(
    (locked: boolean) => {
      if (locked || panesRef.current.length >= MAX_PANES) return;
      const next = createGrokPane(panesRef.current.length);
      setPanes((current) => {
        const result = [...current, next];
        void persistPaneLabels(result);
        return result;
      });
      setFocusedPaneId(next.id);
    },
    [persistPaneLabels],
  );

  const openRemainderChat = useCallback(
    (remainder: string, locked: boolean): boolean => {
      if (locked || panesRef.current.length >= MAX_PANES) return false;
      const next = createGrokPane(panesRef.current.length);
      next.draft = remainder;
      next.modelChoice = "auto";
      next.reasoningEffort = "low";
      setPanes((current) => {
        const result = [...current, next];
        void persistPaneLabels(result);
        return result;
      });
      setFocusedPaneId(next.id);
      return true;
    },
    [persistPaneLabels],
  );

  const removePane = useCallback((id: string) => {
    setPanes((current) => {
      const next = current.filter((pane) => pane.id !== id);
      const result = next.length ? next : [createGrokPane(0)];
      setFocusedPaneId((focused) => (focused === id ? result[0]!.id : focused));
      return result;
    });
  }, []);

  const updatePane = useCallback(
    (id: string, updater: (pane: GrokPaneState) => GrokPaneState) => {
      setPanes((current) => current.map((pane) => (pane.id === id ? updater(pane) : pane)));
    },
    [],
  );

  const loadConversationInto = useCallback(
    async (paneId: string, conversationId: string, cryptoStatus: MessageCryptoStatus | null) => {
      if (!isConversationId(conversationId)) {
        toast.error(INVALID_CHAT_TOAST);
        return;
      }
      if (cryptoStatus?.enabled && !CRYPTO_UNLOCKED.value) {
        return;
      }
      try {
        const detail = await api.chatConversation(conversationId);
        const messages = await Promise.all(
          detail.messages.map(async (item) => ({
            id: item.id,
            role: item.role as "user" | "assistant",
            content: await decryptStoredMessage(item),
            files: item.files?.map((file) => ({
              media_id: file.media_id,
              filename: file.filename,
              content_type: file.content_type,
              kind: file.kind,
              url: file.url,
              byte_size: file.byte_size,
              extract_text: file.extract_text,
            })),
            routeLabel:
              item.role === "assistant" ? spendChipLabel(detail.last_model, detail.last_reasoning) : null,
          })),
        );
        setPanes((current) =>
          current.map((pane) =>
            pane.id !== paneId
              ? pane
              : {
                  ...pane,
                  conversationId: detail.id,
                  createNonce: detail.id,
                  modelChoice: detail.model || "auto",
                  lastResolvedModel: detail.last_model ?? null,
                  reasoningEffort: isGrokReasoningEffort(detail.reasoning) ? detail.reasoning : "low",
                  lastResolvedReasoning: detail.last_reasoning ?? null,
                  savedNoteId: detail.saved_note_id ?? null,
                  conversationTitle: detail.title || null,
                  messages,
                  recapQuestion: Boolean(detail.recap_question),
                },
          ),
        );
      } catch (error) {
        if (error instanceof ApiError && (error.status === 422 || error.status === 400)) {
          toast.error(INVALID_CHAT_TOAST);
        }
        setPanes((current) =>
          current.map((pane) =>
            pane.id === paneId && pane.conversationId === conversationId
              ? { ...pane, conversationId: null, createNonce: null }
              : pane,
          ),
        );
      }
    },
    [],
  );

  const startNewChat = useCallback(
    () => {
      updatePane(focusedPaneIdRef.current, (pane) => ({
        ...pane,
        conversationId: null,
        createNonce: null,
        messages: [],
        recapQuestion: false,
        pendingAttachments: [],
        savedNoteId: null,
        conversationTitle: null,
      }));
    },
    [updatePane],
  );

  const loadConversation = useCallback(
    async (conversationId: string, cryptoStatus: MessageCryptoStatus | null, restoredConversations: Set<string>) => {
      if (!isConversationId(conversationId)) {
        toast.error(INVALID_CHAT_TOAST);
        return;
      }
      restoredConversations.add(conversationId);
      await loadConversationInto(focusedPaneIdRef.current, conversationId, cryptoStatus);
      updatePane(focusedPaneIdRef.current, (pane) => ({ ...pane, draft: "", pendingAttachments: [] }));
    },
    [loadConversationInto, updatePane],
  );

  const deleteConversation = useCallback(
    async (row: GrokConversation) => {
      if (!window.confirm(`Delete "${row.title}"? This cannot be undone.`)) return;
      try {
        await api.deleteChatConversation(row.id);
        const focused = panesRef.current.find((pane) => pane.id === focusedPaneIdRef.current);
        const clearedFocused = focused?.conversationId === row.id;
        setPanes((current) =>
          current.map((pane) =>
            pane.conversationId === row.id
              ? {
                  ...pane,
                  conversationId: null,
                  createNonce: null,
                  messages: [],
                  draft: "",
                  recapQuestion: false,
                  pendingAttachments: [],
                  savedNoteId: null,
                  conversationTitle: null,
                }
              : pane,
          ),
        );
        if (clearedFocused) startNewChat();
      } catch (error) {
        toastActionError(error, "delete chat", "Could not delete that chat");
      }
    },
    [startNewChat],
  );

  return {
    panes,
    setPanes,
    focusedPaneId,
    setFocusedPaneId,
    focusedPaneIdRef,
    panesRef,
    addPane,
    openRemainderChat,
    removePane,
    updatePane,
    loadConversationInto,
    loadConversation,
    startNewChat,
    deleteConversation,
    persistPaneLabels,
  };
}

// Re-export utilities for convenience
export { loadSavedGrokPanes, saveGrokPanes, createGrokPane, grokModelLabel, isGrokReasoningEffort };
