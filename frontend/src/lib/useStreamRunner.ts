"use client";

import { toast } from "sonner";
import { ApiError, api } from "@/lib/api";
import { EMPTY_REPLY_BODY, NO_REPLY_TOAST, normalizeTurnStatus, type ChatStatusKind } from "@/lib/grok-pane-name";
import { restoreDraftAfterSilent } from "@/lib/silent-retry";

type IncludeMode = "auto" | "selection" | "heading" | "chunk";

type StreamFile = {
  media_id?: string;
  filename?: string;
  content_type?: string;
  kind?: string;
  url?: string;
};

type StreamLine = {
  id: string;
  role: "user" | "assistant";
  content: string;
  files?: StreamFile[] | null;
  error?: string | null;
  failed?: boolean;
  waiting?: boolean;
  turnStatus?: string | null;
  routeLabel?: string | null;
  paceNote?: string | null;
  includeChip?: string | null;
  includeHasMore?: boolean;
  includeNextOffset?: number | null;
  includeNextHeading?: string | null;
  calendarProposal?: { title?: string; start?: string; end?: string; status?: string };
  mailProposal?: { to?: string; subject?: string; body?: string; status?: string };
};

type StreamPane = {
  modelChoice: string;
  reasoningEffort: string;
  conversationId: string | null;
  conversationTitle: string | null;
  displayName: string;
  messages: StreamLine[];
  draft: string;
  includeArticle: boolean;
  includeNoteId: string | null;
  workingNoteId: string | null;
  includeMode: IncludeMode;
  includeHeading: string | null;
  includeOffset: number;
  recapQuestion: boolean;
  lastResolvedModel: string | null;
  lastResolvedReasoning: string | null;
  streamStatus?: string | null;
};

type UseStreamRunnerOptions = {
  pane: StreamPane;
  onUpdate: (updater: (current: StreamPane) => any) => void;
  onHistoryChanged?: () => void;
  voice: {
    userStoppedTtsRef: { current: boolean };
    streamAssistantIdRef: { current: string | null };
    requestAutoListen: (messageId: string, markdown: string) => void;
    messagesRef: { current: Array<{ id: string; content?: string | null }> };
  };
  abortRef: { current: AbortController | null };
  abortingRef: { current: boolean };
  turnIdRef: { current: number };
  setAborting: (aborting: boolean) => void;
  setBusy: (busy: boolean) => void;
  setStreamStatus: (status: ChatStatusKind | null) => void;
  setInFlightSpend: (spend: string | null) => void;
  applyStreamStatus: (
    kind:
      | "working"
      | "queued"
      | "thinking"
      | "writing"
      | "generating"
      | "searching"
      | "starting_agent"
      | "deploying"
      | "error"
      | null,
  ) => void;
  clearStreamStatus: () => void;
  markWriting: () => void;
  ensureOwnedConversation: () => Promise<string>;
  turnSpendRef: { current: { model: string; reasoning: string } };
  draftValueRef: { current: string };
  gotDeltaRef: { current: boolean };
  generatingRef: { current: boolean };
  articleId: string | null;
  label: string;
  persist: boolean;
  messageCryptoEnabled: boolean;
  offerPasteSplit: (draft: string) => void;
  postedSpendForTurn: (modelChoice: string, reasoningEffort: string, message: string) => { model: string; reasoning: string };
  spendChipLabel: (model?: string | null, reasoning?: string | null) => string;
  conversationIdForRequest: (value: string | null | undefined) => string | null;
  INVALID_CHAT_TOAST: string;
  GROK_CONTEXT_THREAD_WINDOW: number;
  encryptMessageBody: (plaintext: string) => Promise<{ iv: string; ct: string }>;
  decryptStoredMessage: (message: {
    id: string;
    role: "user" | "assistant";
    content?: string | null;
    iv?: string | null;
    ct?: string | null;
    encrypted?: boolean;
  }) => Promise<string>;
  MEDIA_MARKDOWN: { test: (value: string) => boolean };
  formatChatError: (status: number, detail: string, assistantName?: string) => string;
  chatCreateErrorToast: (status: number, message: string) => string | null;
  withAssistantName: (message: string, assistantName?: string) => string;
  isOversizedPasteHttp: (status: number, detail: string) => boolean;
  PASTE_FIRST_CHUNK_CHARS: number;
  readableXaiToast: (message: string) => string;
  chatTimeoutToast: (status: number, message: string) => string | null;
  isSilentEmptyChatDetail: (message: string) => boolean;
  pasteSplitToast: (chars: number) => string;
  hasMediaImage: (content: string | null | undefined) => boolean;
  toastActionError: (error: unknown, action: string, fallback: string) => void;
  savedReplyFillsEmptyBubble: (localContent: string, savedText: string) => boolean;
};

export function useStreamRunner({
  pane,
  onUpdate,
  onHistoryChanged,
  voice,
  abortRef,
  abortingRef,
  turnIdRef,
  setAborting,
  setBusy,
  setStreamStatus,
  setInFlightSpend,
  applyStreamStatus,
  clearStreamStatus,
  markWriting,
  ensureOwnedConversation,
  turnSpendRef,
  draftValueRef,
  gotDeltaRef,
  generatingRef,
  articleId,
  label,
  persist,
  messageCryptoEnabled,
  offerPasteSplit,
  postedSpendForTurn,
  spendChipLabel,
  conversationIdForRequest,
  INVALID_CHAT_TOAST,
  GROK_CONTEXT_THREAD_WINDOW,
  encryptMessageBody,
  decryptStoredMessage,
  MEDIA_MARKDOWN,
  formatChatError,
  chatCreateErrorToast,
  withAssistantName,
  isOversizedPasteHttp,
  PASTE_FIRST_CHUNK_CHARS,
  readableXaiToast,
  chatTimeoutToast,
  isSilentEmptyChatDetail,
  pasteSplitToast,
  hasMediaImage,
  toastActionError,
  savedReplyFillsEmptyBubble,
}: UseStreamRunnerOptions) {
    async function runStream(options: {
      message: string;
      retry?: boolean;
      userLine?: StreamLine;
      assistantId: string;
      mediaIds?: string[];
      includeMode?: IncludeMode;
      includeHeading?: string | null;
      includeSelection?: string | null;
      includeOffset?: number;
      controller?: AbortController;
      turnId?: number;
      silentRetried?: boolean;
    }) {
      const { message, retry = false, userLine, assistantId } = options;
      const turnId = options.turnId ?? turnIdRef.current;
      const controller = options.controller ?? new AbortController();
      if (turnId !== turnIdRef.current || controller.signal.aborted) return;
      voice.userStoppedTtsRef.current = false;
      voice.streamAssistantIdRef.current = assistantId;
      abortRef.current = controller;
      abortingRef.current = false;
      setAborting(false);
      const posted = postedSpendForTurn(pane.modelChoice, pane.reasoningEffort, message);
      turnSpendRef.current = posted;
      setInFlightSpend(spendChipLabel(posted.model, posted.reasoning));
      onUpdate((current) => ({
        ...current,
        lastResolvedModel: posted.model,
        lastResolvedReasoning: posted.reasoning,
      }));

      setBusy(true);
      let streamFailed = false;
      let holdSilentRetry = false;
      const sentText = (userLine?.content || "").trim();
      const putSentBack = (reply: string) => {
        onUpdate((current) => {
          const next = restoreDraftAfterSilent(current.draft, sentText, reply);
          if (next === current.draft) return current;
          draftValueRef.current = next;
          return { ...current, draft: next };
        });
      };
      let streamedText = "";
      let conversationId: string | null = conversationIdForRequest(pane.conversationId);
      try {
        conversationId = conversationIdForRequest(pane.conversationId);
        if (persist && !retry) {
          conversationId = await ensureOwnedConversation();
        }
        if (persist && !conversationId) {
          throw new ApiError(422, INVALID_CHAT_TOAST);
        }
        const threadRows = pane.messages.filter((item) => item.id !== assistantId && item.content?.trim());
        const windowedRows = threadRows.slice(-GROK_CONTEXT_THREAD_WINDOW);
        const historyOverride = messageCryptoEnabled
          ? [
              ...windowedRows.map((item) => ({ role: item.role, content: item.content || "" })),
              ...(retry || !userLine ? [] : [{ role: "user" as const, content: userLine.content || message }]),
            ].slice(-GROK_CONTEXT_THREAD_WINDOW)
          : undefined;
        const clientTitle =
          messageCryptoEnabled && !retry && !pane.conversationTitle && userLine?.content
            ? userLine.content.trim().split("\n", 1)[0]?.slice(0, 80)
            : undefined;
        if (messageCryptoEnabled && conversationId && userLine && !retry) {
          const blob = await encryptMessageBody(userLine.content || message);
          const saved = await api.postEncryptedMessage(conversationId, {
            role: "user",
            iv: blob.iv,
            ct: blob.ct,
            id: userLine.id,
            title: clientTitle,
            media_ids: options.mediaIds,
          });
          if (saved.id !== userLine.id) {
            onUpdate((current) => ({
              ...current,
              messages: current.messages.map((item) =>
                item.id === userLine.id ? { ...item, id: saved.id } : item,
              ),
            }));
          }
        }
        await api.streamChat(
          {
            message,
            retry,
            conversation_id: conversationId,
            model: pane.modelChoice,
            reasoning_effort: pane.modelChoice === "auto" ? "auto" : pane.reasoningEffort,
            article_id: articleId,
            include_article: Boolean(pane.includeArticle && articleId),
            include_note_id: pane.includeNoteId || undefined,
            working_note_id: pane.workingNoteId || undefined,
            include_mode: options.includeMode || pane.includeMode,
            include_selection: options.includeSelection || undefined,
            include_heading: options.includeHeading || pane.includeHeading || undefined,
            include_offset: options.includeOffset ?? pane.includeOffset ?? 0,
            recap_question: pane.recapQuestion,
            media_ids: retry ? undefined : options.mediaIds,
            history_override: historyOverride,
            client_title: clientTitle,
            pane_name: pane.displayName,
          },
          (delta) => {
            if (turnId !== turnIdRef.current) return;
            if ((delta || "").trim()) gotDeltaRef.current = true;
            const generating = generatingRef.current;
            if (!generating) markWriting();
            onUpdate((current) => ({
              ...current,
              streamStatus: generating ? "generating" : "writing",
              messages: current.messages.map((item) => {
                if (item.id !== assistantId) return item;
                const nextContent = MEDIA_MARKDOWN.test(delta) ? delta : item.content + delta;
                streamedText = nextContent;
                return {
                  ...item,
                  waiting: true,
                  turnStatus: generating ? "writing" : "writing",
                  content: nextContent,
                  failed: false,
                  error: null,
                };
              }),
            }));
          },
          (meta) => {
            if (turnId !== turnIdRef.current) return;
            if (
              meta.stream_status === "working" ||
              meta.stream_status === "queued" ||
              meta.stream_status === "thinking" ||
              meta.stream_status === "writing" ||
              meta.stream_status === "generating" ||
              meta.stream_status === "searching" ||
              meta.stream_status === "starting_agent" ||
              meta.stream_status === "deploying"
            ) {
              applyStreamStatus(meta.stream_status);
              const turn = normalizeTurnStatus(meta.stream_status);
              if (turn && turn !== "done") {
                onUpdate((current) => ({
                  ...current,
                  messages: current.messages.map((item) =>
                    item.id === assistantId && !item.content
                      ? { ...item, waiting: true, turnStatus: turn, failed: false }
                      : item,
                  ),
                }));
              }
            }
            if (meta.toast) {
              if (meta.toast_kind === "error") toast.error(meta.toast);
              else toast.message(meta.toast);
            }
            onUpdate((current) => {
              let next = current;
              if (meta.conversation_id && meta.conversation_id !== current.conversationId) {
                const firstUser = current.messages.find((item) => item.role === "user")?.content || "";
                next = {
                  ...next,
                  conversationId: meta.conversation_id,
                  conversationTitle: current.conversationTitle || firstUser.trim().split("\n")[0] || null,
                };
              }
              if (meta.user_message_id && userLine) {
                next = {
                  ...next,
                  messages: next.messages.map((item) =>
                    item.id === userLine.id ? { ...item, id: meta.user_message_id! } : item,
                  ),
                };
              }
              if (meta.assistant_message_id) {
                voice.streamAssistantIdRef.current = meta.assistant_message_id;
                next = {
                  ...next,
                  messages: next.messages.map((item) =>
                    item.id === assistantId
                      ? {
                          ...item,
                          id: meta.assistant_message_id!,
                          failed: meta.partial ? item.failed : item.failed,
                          error: meta.partial ? item.error : item.error,
                        }
                      : item,
                  ),
                };
              }
              if (meta.model) {
                next = { ...next, lastResolvedModel: meta.model };
              }
              if (meta.reasoning_effort) {
                next = { ...next, lastResolvedReasoning: meta.reasoning_effort };
              }
              if (meta.include_chip) {
                next = {
                  ...next,
                  includeOffset: meta.include_next_offset ?? next.includeOffset,
                  includeHeading: meta.include_next_heading ?? next.includeHeading,
                  includeMode: meta.include_has_more
                    ? meta.include_next_heading
                      ? "heading"
                      : "chunk"
                    : next.includeMode,
                  messages: next.messages.map((item) =>
                    item.id === assistantId || item.id === userLine?.id
                      ? {
                          ...item,
                          includeChip: meta.include_chip,
                          includeHasMore: item.role === "assistant" ? Boolean(meta.include_has_more) : item.includeHasMore,
                          includeNextOffset: meta.include_next_offset ?? null,
                          includeNextHeading: meta.include_next_heading ?? null,
                        }
                      : item,
                  ),
                };
              }
              if (meta.calendar_proposal) {
                next = {
                  ...next,
                  messages: next.messages.map((item) =>
                    item.id === assistantId || item.id === meta.assistant_message_id
                      ? {
                          ...item,
                          calendarProposal: { ...meta.calendar_proposal!, status: "pending" },
                        }
                      : item,
                  ),
                };
              }
              if (meta.mail_proposal) {
                next = {
                  ...next,
                  messages: next.messages.map((item) =>
                    item.id === assistantId || item.id === meta.assistant_message_id
                      ? {
                          ...item,
                          mailProposal: { ...meta.mail_proposal!, status: "pending" },
                        }
                      : item,
                  ),
                };
              }
              if (meta.media_id) {
                const targetId = meta.assistant_message_id || assistantId;
                next = {
                  ...next,
                  messages: next.messages.map((item) =>
                    item.id === targetId || item.id === assistantId
                      ? {
                          ...item,
                          files: [
                            ...(item.files || []).filter((file) => file.media_id !== meta.media_id),
                            {
                              media_id: meta.media_id!,
                              filename: "generated image",
                              content_type: "image/png",
                              kind: "image" as const,
                              url: `/api/v1/media/${meta.media_id}`,
                            },
                          ],
                        }
                      : item,
                  ),
                };
              }
              if (meta.model || meta.reasoning_effort) {
                const model = meta.model || turnSpendRef.current.model;
                const reasoning = meta.reasoning_effort || turnSpendRef.current.reasoning;
                turnSpendRef.current = { model, reasoning };
                const spend = spendChipLabel(model, reasoning);
                setInFlightSpend(spend);
                const targetId = meta.assistant_message_id || assistantId;
                next = {
                  ...next,
                  messages: next.messages.map((item) =>
                    item.id === targetId || item.id === assistantId ? { ...item, routeLabel: spend } : item,
                  ),
                };
              }
              if (meta.pace_note) {
                const paceId = meta.assistant_message_id || assistantId;
                next = {
                  ...next,
                  messages: next.messages.map((item) =>
                    item.id === paceId || item.id === assistantId ? { ...item, paceNote: meta.pace_note } : item,
                  ),
                };
              }
              return next;
            });
            if (meta.conversation_id || meta.assistant_message_id) onHistoryChanged?.();
          },
          controller.signal,
          () => {
            if (turnId !== turnIdRef.current) return;
            if (!gotDeltaRef.current) applyStreamStatus("thinking");
          },
        );
      } catch (error) {
        if (turnId !== turnIdRef.current) return;
        streamFailed = true;
        const aborted = controller.signal.aborted && !(error instanceof ApiError);
        if (aborted) {
          onUpdate((current) => ({
            ...current,
            streamStatus: null,
            messages: current.messages.map((item) => {
              if (item.role !== "assistant" || !(item.waiting || item.id === assistantId)) return item;
              const kept = (item.content || "").trim();
              return {
                ...item,
                waiting: false,
                turnStatus: kept ? ("done" as const) : ("error" as const),
                failed: !kept,
                error: kept ? null : "Stopped.",
                content: item.content,
              };
            }),
          }));
          return;
        }
        const status = error instanceof ApiError ? error.status : 502;
        const detail = error instanceof ApiError ? error.message : `${label} did not reply`;
        const createToast = error instanceof ApiError ? chatCreateErrorToast(status, detail) : null;
        const formatted = createToast
          ? createToast
          : detail.startsWith("Chat failed (HTTP")
            ? withAssistantName(detail, label)
            : formatChatError(status, detail, label);
        const oversizedPaste = isOversizedPasteHttp(status, detail);
        const turnText = userLine?.content || message;
        if (oversizedPaste && turnText.length >= PASTE_FIRST_CHUNK_CHARS) {
          offerPasteSplit(turnText);
        }
        const imageFail = generatingRef.current || /did not return an image|could not generate that image/i.test(detail);
        const shortImage = readableXaiToast(detail);
        const capDetail = /over the cap|too long|Recent messages are too long/i.test(detail) ? detail : null;
        const timeoutDetail = chatTimeoutToast(status, detail);
        const silentEmpty = !imageFail && isSilentEmptyChatDetail(detail);
        if (silentEmpty && !options.silentRetried) {
          holdSilentRetry = true;
          streamFailed = false;
          gotDeltaRef.current = false;
          streamedText = "";
          setStreamStatus("thinking");
          onUpdate((current) => ({
            ...current,
            streamStatus: "thinking",
            messages: current.messages.map((item) =>
              item.id === assistantId || item.waiting
                ? { ...item, content: "", waiting: true, turnStatus: "thinking" as const, failed: false, error: null }
                : item,
            ),
          }));
          await runStream({
            message,
            retry: true,
            silentRetried: true,
            userLine,
            assistantId,
            mediaIds: options.mediaIds,
            includeMode: options.includeMode,
            includeHeading: options.includeHeading,
            includeSelection: options.includeSelection,
            includeOffset: options.includeOffset,
            controller,
            turnId,
          });
          return;
        }
        if (silentEmpty) {
          setStreamStatus(null);
          putSentBack(EMPTY_REPLY_BODY);
          onUpdate((current) => ({
            ...current,
            streamStatus: null,
            messages: current.messages.map((item) => {
              const target = item.role === "assistant" && (item.waiting || item.id === assistantId);
              if (!target) return item;
              const kept = (item.content || "").trim();
              const keepText = Boolean(kept) && !isSilentEmptyChatDetail(kept);
              return {
                ...item,
                waiting: false,
                turnStatus: "done" as const,
                failed: false,
                error: null,
                content: keepText ? item.content : EMPTY_REPLY_BODY,
              };
            }),
          }));
          return;
        }
        const toastText = imageFail
          ? (shortImage.length > 180 ? "Could not generate that image." : shortImage)
          : capDetail
            ? capDetail
            : timeoutDetail && status === 504
              ? timeoutDetail
              : oversizedPaste && turnText.length >= PASTE_FIRST_CHUNK_CHARS
                ? pasteSplitToast(turnText.length)
                : status === 413 || status === 400
                  ? detail
                  : status === 502
                    ? readableXaiToast(detail)
                    : NO_REPLY_TOAST;
        onUpdate((current) => ({
          ...current,
          streamStatus: "error",
          draft: oversizedPaste && (userLine?.content || message) ? userLine?.content || message : current.draft,
          messages: current.messages.map((item) => {
            const target = item.role === "assistant" && (item.waiting || item.id === assistantId);
            if (!target) return item;
            const kept = (item.content || "").trim();
            const wipePlaceholder =
              !hasMediaImage(item.content) &&
              !/\/api\/v1\/media\//.test(item.content) &&
              /Generating the image|Here's the image|implemented and passing/i.test(item.content);
            const empty = wipePlaceholder || !kept;
            const bubble = empty
              ? imageFail
                ? shortImage || "Could not generate that image."
                : formatted || EMPTY_REPLY_BODY
              : item.content;
            const softEmpty =
              empty &&
              !imageFail &&
              (bubble === EMPTY_REPLY_BODY ||
                /didn't get a text reply|xai silent|returned no text/i.test(bubble));
            return {
              ...item,
              waiting: false,
              turnStatus: softEmpty ? ("done" as const) : ("error" as const),
              failed: !softEmpty,
              error: softEmpty ? null : imageFail ? shortImage || "Could not generate that image." : formatted,
              content: empty ? bubble : item.content,
            };
          }),
        }));
        applyStreamStatus("error");
        if (
          !oversizedPaste &&
          toastText !== NO_REPLY_TOAST &&
          !/didn't get a text reply|xai silent|returned no text/i.test(toastText)
        ) {
          toast.error(toastText);
        }
      } finally {
        if (turnId !== turnIdRef.current) return;
        if (holdSilentRetry) return;
        if (abortRef.current === controller) abortRef.current = null;
        abortingRef.current = false;
        setAborting(false);
        setBusy(false);
        if (streamFailed) return;
        const hasReply =
          gotDeltaRef.current ||
          Boolean(streamedText.trim()) ||
          hasMediaImage(streamedText) ||
          /\/api\/v1\/media\//.test(streamedText);
        if (hasReply) {
          if (isSilentEmptyChatDetail(streamedText)) putSentBack(streamedText);
          clearStreamStatus();
          onUpdate((current) => ({
            ...current,
            streamStatus: null,
            messages: current.messages.map((item) =>
              item.id === assistantId || item.waiting
                ? { ...item, waiting: false, turnStatus: "done" as const, failed: false, error: null }
                : item,
            ),
          }));
          if (messageCryptoEnabled && conversationId && streamedText.trim()) {
            try {
              const blob = await encryptMessageBody(streamedText);
              await api.postEncryptedMessage(conversationId, {
                role: "assistant",
                iv: blob.iv,
                ct: blob.ct,
                id: voice.streamAssistantIdRef.current || assistantId,
              });
            } catch (error) {
              toastActionError(error, "save encrypted reply", "Could not save the encrypted reply.");
            }
          }
          voice.requestAutoListen(voice.streamAssistantIdRef.current || assistantId, streamedText);
          return;
        }
        let recovered = "";
        let recoveredId = "";
        if (conversationId && persist) {
          try {
            const detail = await api.chatConversation(conversationId);
            const last = [...detail.messages].reverse().find((item) => item.role === "assistant");
            if (last) {
              const saved = (await decryptStoredMessage(last)).trim();
              const already = voice.messagesRef.current.find((item) => item.id === last.id);
              const alreadyShown =
                Boolean(already && (already.content || "").trim()) &&
                !isSilentEmptyChatDetail(already?.content || "");
              if (!alreadyShown && savedReplyFillsEmptyBubble(streamedText, saved)) {
                recovered = saved;
                recoveredId = last.id;
              }
            }
          } catch {
            /* the bubble keeps the empty-reply sentence */
          }
        }
        if (recovered) {
          streamedText = recovered;
          setStreamStatus(null);
          onUpdate((current) => ({
            ...current,
            streamStatus: null,
            messages: current.messages.map((item) =>
              item.id === assistantId || item.id === recoveredId || (item.role === "assistant" && item.waiting)
                ? {
                    ...item,
                    id: recoveredId || item.id,
                    waiting: false,
                    turnStatus: "done" as const,
                    failed: false,
                    error: null,
                    content: recovered,
                  }
                : item,
            ),
          }));
          voice.requestAutoListen(recoveredId || assistantId, recovered);
          return;
        }
        putSentBack(EMPTY_REPLY_BODY);
        setStreamStatus(null);
        const spoken = streamedText.trim() || EMPTY_REPLY_BODY;
        onUpdate((current) => ({
          ...current,
          streamStatus: null,
          messages: current.messages.map((item) =>
            item.id === assistantId || item.waiting
              ? {
                  ...item,
                  waiting: false,
                  turnStatus: "done" as const,
                  failed: false,
                  error: null,
                  content: item.content?.trim() ? item.content : EMPTY_REPLY_BODY,
                }
              : item,
          ),
        }));
        voice.requestAutoListen(voice.streamAssistantIdRef.current || assistantId, spoken);
      }
    }
  return { runStream };
}
