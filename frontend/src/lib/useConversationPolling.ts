"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { toast } from "sonner";
import { api, ApiError } from "@/lib/api";
import { agentFollowUpPending } from "@/lib/agent-followup";
import { INVALID_CHAT_TOAST, isConversationId } from "@/lib/chat-conversation";
import { decryptStoredMessage } from "@/lib/message-crypto";
import {
  juniorNotice,
  messagesNewerThan,
  shouldShowJuniorNotice,
} from "@/lib/junior-message-notice";
import { comparePinned } from "@/lib/pin-order";
import type { GrokConversation, MessageCryptoStatus } from "@/lib/types";
import type { GrokPaneState } from "@/components/grok-pane";

const POLL_INTERVAL_MS = 20000;

export type PublishJuniorNoticeFn = (
  conversationId: string,
  conversationTitle: string | null,
  messages: { id: string; role: string; content: string; created_at?: string }[],
) => void;

export function useConversationPolling(
  persist: boolean,
  needsCryptoUnlock: boolean,
  panesRef: React.MutableRefObject<GrokPaneState[]>,
  openRef: React.MutableRefObject<boolean>,
  focusedPaneIdRef: React.MutableRefObject<string>,
  seenMessageIdsRef: React.MutableRefObject<Set<string>>,
  cryptoStatus: MessageCryptoStatus | null,
  setNoticeCount: (updater: (count: number) => number) => void,
  setOpen: (open: boolean) => void,
  setPanes: (updater: (current: GrokPaneState[]) => GrokPaneState[]) => void,
  loadConversation: (conversationId: string) => void | Promise<void>,
) {
  const [conversations, setConversations] = useState<GrokConversation[]>([]);
  const [historyLoading, setHistoryLoading] = useState(false);
  const [renamingId, setRenamingId] = useState<string | null>(null);
  const [renameDraft, setRenameDraft] = useState("");
  const renameInputRef = useRef<HTMLInputElement>(null);
  const conversationListReadyRef = useRef(false);
  const conversationUpdatedRef = useRef(new Map<string, string>());

  const refreshHistory = useCallback(async () => {
    if (!persist) return;
    setHistoryLoading(true);
    try {
      setConversations(await api.chatConversations());
    } catch {
      /* ignore */
    } finally {
      setHistoryLoading(false);
    }
  }, [persist]);

  const publishJuniorNotice = useCallback<PublishJuniorNoticeFn>(
    (conversationId, conversationTitle, messages) => {
      const focused = panesRef.current.find((pane) => pane.id === focusedPaneIdRef.current);
      const liveStream = panesRef.current.some(
        (pane) => pane.conversationId === conversationId && Boolean(pane.streamStatus),
      );
      if (
        !shouldShowJuniorNotice({
          panelOpen: openRef.current,
          documentHidden: document.hidden,
          focusedConversationId: focused?.conversationId ?? null,
          conversationId,
          liveStream,
        })
      ) {
        return;
      }
      const notice = juniorNotice({ conversationId, conversationTitle, messages });
      if (!notice) return;
      toast(notice.title, { description: notice.body });
      if (!openRef.current) setNoticeCount((count) => count + 1);
      if (typeof Notification === "undefined" || Notification.permission !== "granted") return;
      const posted = new Notification(notice.title, { body: notice.body, tag: conversationId });
      posted.onclick = () => {
        window.focus();
        setOpen(true);
        void loadConversation(conversationId);
      };
    },
    [panesRef, focusedPaneIdRef, openRef, setNoticeCount, setOpen, loadConversation],
  );

  const refreshAgentMessages = useCallback(
    async (paneId: string, conversationId: string) => {
      try {
        const detail = await api.chatConversation(conversationId);
        const incoming = await Promise.all(
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
          })),
        );
        const pane = panesRef.current.find(
          (item) => item.id === paneId && item.conversationId === conversationId,
        );
        if (!pane) return;
        const known = new Set(pane.messages.map((item) => item.id));
        const extra = incoming.filter(
          (item) => !known.has(item.id) && !seenMessageIdsRef.current.has(item.id),
        );
        if (!extra.length) return;
        for (const item of extra) seenMessageIdsRef.current.add(item.id);
        publishJuniorNotice(conversationId, pane.conversationTitle || pane.displayName, extra);
        setPanes((current) =>
          current.map((item) => {
            if (item.id !== paneId || item.conversationId !== conversationId) return item;
            const have = new Set(item.messages.map((message) => message.id));
            const added = extra.filter((message) => !have.has(message.id));
            if (!added.length) return item;
            return { ...item, messages: [...item.messages, ...added] };
          }),
        );
      } catch {
        // Leave the open thread in place. The next poll retries.
      }
    },
    [panesRef, seenMessageIdsRef, publishJuniorNotice, setPanes],
  );

  const pollConversationNotices = useCallback(async () => {
    if (!persist) return;
    try {
      const rows = await api.chatConversations();
      if (!conversationListReadyRef.current) {
        for (const row of rows) conversationUpdatedRef.current.set(row.id, row.updated_at);
        conversationListReadyRef.current = true;
        return;
      }
      const watched = new Set(
        panesRef.current
          .filter((pane) => pane.conversationId && agentFollowUpPending(pane.messages))
          .map((pane) => pane.conversationId as string),
      );
      for (const row of rows) {
        const previous = conversationUpdatedRef.current.get(row.id);
        conversationUpdatedRef.current.set(row.id, row.updated_at);
        if (!previous || previous === row.updated_at || watched.has(row.id)) continue;
        if (panesRef.current.some((pane) => pane.conversationId === row.id && pane.streamStatus)) continue;
        const detail = await api.chatConversation(row.id);
        const incoming = await Promise.all(
          detail.messages.map(async (item) => ({
            id: item.id,
            role: item.role,
            content: await decryptStoredMessage(item),
            created_at: item.created_at,
          })),
        );
        const newer = messagesNewerThan(incoming, previous).filter(
          (item) => !seenMessageIdsRef.current.has(item.id),
        );
        for (const item of incoming) seenMessageIdsRef.current.add(item.id);
        if (!newer.length) continue;
        publishJuniorNotice(row.id, row.title, newer);
        setPanes((current) =>
          current.map((pane) => {
            if (pane.conversationId !== row.id) return pane;
            const have = new Set(pane.messages.map((message) => message.id));
            const added = newer.filter((message) => !have.has(message.id));
            if (!added.length) return pane;
            return { ...pane, messages: [...pane.messages, ...added] };
          }),
        );
      }
    } catch {
      // The next poll retries.
    }
  }, [persist, panesRef, seenMessageIdsRef, publishJuniorNotice, setPanes]);

  useEffect(() => {
    if (!persist || needsCryptoUnlock) return;
    const timer = window.setInterval(() => {
      for (const pane of panesRef.current) {
        if (pane.streamStatus) continue;
        if (!pane.conversationId || !agentFollowUpPending(pane.messages)) continue;
        void refreshAgentMessages(pane.id, pane.conversationId);
      }
      void pollConversationNotices();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(timer);
  }, [persist, needsCryptoUnlock, panesRef, refreshAgentMessages, pollConversationNotices]);

  const pinConversation = useCallback(
    async (row: GrokConversation) => {
      const pinned = !row.pinned;
      try {
        const updated = await api.patchChatConversation(row.id, { pinned });
        setConversations((current) => {
          const next = current.map((item) =>
            item.id === row.id ? { ...item, ...updated, pinned } : item,
          );
          next.sort((a, b) =>
            comparePinned(a, b, (left, right) =>
              (right.updated_at || "").localeCompare(left.updated_at || ""),
            ),
          );
          return next;
        });
      } catch (error) {
        toast.error(error instanceof ApiError ? error.message : "Could not pin that chat");
      }
    },
    [],
  );

  const startRename = useCallback((row: GrokConversation) => {
    setRenamingId(row.id);
    setRenameDraft(row.title);
    window.requestAnimationFrame(() => renameInputRef.current?.select());
  }, []);

  const cancelRename = useCallback(() => {
    setRenamingId(null);
    setRenameDraft("");
  }, []);

  const commitRename = useCallback(
    async (conversationId: string) => {
      if (!persist) return;
      if (!isConversationId(conversationId)) {
        toast.error(INVALID_CHAT_TOAST);
        return;
      }
      const draft = renameDraft;
      setRenamingId(null);
      setRenameDraft("");
      try {
        const updated = await api.patchChatConversation(conversationId, { title: draft });
        setConversations((current) =>
          current.map((row) =>
            row.id === conversationId ? { ...row, title: updated.title } : row,
          ),
        );
        setPanes((current) =>
          current.map((pane) =>
            pane.conversationId === conversationId
              ? { ...pane, conversationTitle: updated.title }
              : pane,
          ),
        );
      } catch {
        /* ignore */
      }
    },
    [persist, renameDraft, setPanes],
  );

  return {
    conversations,
    setConversations,
    historyLoading,
    refreshHistory,
    renamingId,
    renameDraft,
    setRenameDraft,
    renameInputRef,
    pinConversation,
    commitRename,
    startRename,
    cancelRename,
    refreshAgentMessages,
    pollConversationNotices,
    conversationListReadyRef,
    conversationUpdatedRef,
  };
}
