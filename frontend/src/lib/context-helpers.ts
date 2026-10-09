import { toast } from "sonner";

type ContextMessage = {
  role?: string;
  content?: string | null;
  waiting?: boolean;
  files?: Array<{ extract_text?: string | null } | null> | null;
};

type ContextSlice = { chars?: number } | null;

type ContextPane = {
  messages: ContextMessage[];
  includeNoteId: string | null;
  includeArticle: boolean;
  pendingAttachments?: Array<{ extract_text?: string | null }> | null;
};

type ContextValue = {
  messages: ContextMessage[];
  draft: string;
  includeArticle: boolean;
  articleBody?: string | null;
  includeNote: boolean;
  noteBody: string | null | undefined;
  includeSliceChars?: number;
  workingNoteSliceChars?: number;
  pendingExtracts: Array<string | null | undefined>;
};

type PasteSend = (opts: {
  message?: string;
  keepDraft?: string;
  skipPasteSplit?: boolean;
}) => void | Promise<void>;

export type ContextHelpers = {
  contextInput: (draft: string, extraMessages?: ContextMessage[]) => ContextValue;
  contextTooLarge: (draft: string, extraMessages?: ContextMessage[]) => boolean;
  pasteChunkSize: () => number;
  offerPasteSplit: (draft: string) => void;
};

export function createContextHelpers(deps: {
  pane: ContextPane;
  articleId: string | null;
  articleBody?: string | null;
  plannedIncludeSlice: () => ContextSlice;
  plannedWorkingSlice: () => ContextSlice;
  chatContextOverCap: (input: ContextValue) => boolean;
  estimateChatContextChars: (input: ContextValue) => number;
  GROK_CONTEXT_CHAR_CAP: number;
  PASTE_FIRST_CHUNK_CHARS: number;
  pasteSplitToast: (chars: number) => string;
  splitPasteChunk: (text: string, chunk?: number) => { first: string; remainder: string };
  textareaSelection: (el: HTMLTextAreaElement | null | undefined) => string;
  draftRef: { current: HTMLTextAreaElement | null };
  readerCtx: { selection: string };
  onOpenRemainderChat?: (remainder: string) => boolean;
  send: PasteSend;
  Button: any;
  createElement: (type: any, props?: any, ...children: any[]) => any;
}) {
  const {
    pane,
    articleId,
    articleBody,
    plannedIncludeSlice,
    plannedWorkingSlice,
    chatContextOverCap,
    estimateChatContextChars,
    GROK_CONTEXT_CHAR_CAP,
    PASTE_FIRST_CHUNK_CHARS,
    pasteSplitToast,
    splitPasteChunk,
    textareaSelection,
    draftRef,
    readerCtx,
    onOpenRemainderChat,
    send,
    Button,
    createElement,
  } = deps;

  function contextInput(draft: string, extraMessages: ContextMessage[] = pane.messages): ContextValue {
    const noteBody =
      pane.includeNoteId && articleId && pane.includeNoteId === articleId ? articleBody : null;
    const slice = plannedIncludeSlice();
    const workingSlice = plannedWorkingSlice();
    return {
      messages: extraMessages,
      draft,
      includeArticle: Boolean(pane.includeArticle && articleId),
      articleBody,
      includeNote: Boolean(pane.includeNoteId),
      noteBody,
      includeSliceChars: slice?.chars,
      workingNoteSliceChars: workingSlice?.chars,
      pendingExtracts: (pane.pendingAttachments ?? []).map((item) => item.extract_text),
    };
  }

  function contextTooLarge(draft: string, extraMessages: ContextMessage[] = pane.messages) {
    return chatContextOverCap(contextInput(draft, extraMessages));
  }

  function pasteChunkSize() {
    const used = estimateChatContextChars(contextInput(""));
    const budget = GROK_CONTEXT_CHAR_CAP - used;
    return Math.min(PASTE_FIRST_CHUNK_CHARS, Math.max(1, budget));
  }

  function offerPasteSplit(draft: string) {
    const source = draft;
    const n = source.length;
    toast.custom(
      (id) =>
        createElement(
          "div",
          {
            className:
              "flex w-[min(100%,22rem)] flex-col gap-2 rounded-lg border bg-background p-3 text-sm shadow-md",
          },
          createElement("p", null, pasteSplitToast(n)),
          createElement(
            "div",
            { className: "flex flex-col gap-1" },
            createElement(
              Button,
              {
                type: "button",
                size: "sm",
                className: "h-8 justify-start",
                onClick: () => {
                  toast.dismiss(id);
                  const { first, remainder } = splitPasteChunk(source, pasteChunkSize());
                  void send({ message: first, keepDraft: remainder, skipPasteSplit: true });
                },
              },
              "Send first chunk",
            ),
            createElement(
              Button,
              {
                type: "button",
                size: "sm",
                variant: "outline",
                className: "h-8 justify-start",
                onClick: () => {
                  const selected = textareaSelection(draftRef.current) || readerCtx.selection;
                  if (!selected.trim()) {
                    toast.error("Highlight text in the box, then Include selection.");
                    return;
                  }
                  toast.dismiss(id);
                  void send({
                    message: selected,
                    keepDraft: source,
                    skipPasteSplit: selected.length <= PASTE_FIRST_CHUNK_CHARS,
                  });
                },
              },
              "Include selection",
            ),
            createElement(
              Button,
              {
                type: "button",
                size: "sm",
                variant: "outline",
                className: "h-8 justify-start",
                onClick: () => {
                  toast.dismiss(id);
                  const { first, remainder } = splitPasteChunk(source, pasteChunkSize());
                  let parked = false;
                  if (remainder && onOpenRemainderChat) {
                    parked = Boolean(onOpenRemainderChat(remainder));
                  }
                  if (remainder && !parked) {
                    toast.message("Remainder stayed in this box — Junior is full.");
                  }
                  void send({
                    message: first,
                    keepDraft: remainder && !parked ? remainder : "",
                    skipPasteSplit: true,
                  });
                },
              },
              "New chat with remainder",
            ),
          ),
        ),
      { duration: 30_000 },
    );
  }

  return { contextInput, contextTooLarge, pasteChunkSize, offerPasteSplit };
}
