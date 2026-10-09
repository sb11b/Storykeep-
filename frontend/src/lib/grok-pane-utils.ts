type IncludeMode = "auto" | "selection" | "heading" | "chunk";

type SliceResult = { chip?: string | null; chars?: number };

type SliceInput = {
  body: string;
  mode?: IncludeMode | null;
  selection?: string | null;
  heading?: string | null;
  offset?: number;
  title?: string | null;
  cap?: number;
  hardMax?: number;
};

type SlicePane = {
  workingNoteId: string | null;
  includeArticle: boolean;
  includeMode: IncludeMode;
  includeHeading: string | null;
  includeOffset: number;
  workingNoteTitle: string | null;
};

export function createGrokPane(
  paneIndex = 0,
  deps: {
    loadLastFiling: () => { dest: string; folderId: string | null };
    defaultGrokPaneName: (index: number) => string;
  },
) {
  const last = deps.loadLastFiling();
  return {
    id: crypto.randomUUID(),
    displayName: deps.defaultGrokPaneName(paneIndex),
    conversationId: null,
    createNonce: null,
    modelChoice: "auto",
    lastResolvedModel: null,
    reasoningEffort: "low",
    lastResolvedReasoning: null,
    messages: [],
    draft: "",
    includeArticle: false,
    includeMode: "auto" as const,
    includeHeading: null,
    includeOffset: 0,
    includeNoteId: null,
    includeNoteTitle: null,
    workingNoteId: null,
    workingNoteTitle: null,
    noteDest: last.dest,
    noteFolderId: last.folderId,
    recapQuestion: false,
    pendingAttachments: [],
    streamStatus: null,
    savedNoteId: null,
    conversationTitle: null,
  };
}

/** Keep controlled textarea in sync when STT inserts before React re-renders. */
export function setNativeTextareaValue(el: HTMLTextAreaElement, value: string) {
  const desc = Object.getOwnPropertyDescriptor(HTMLTextAreaElement.prototype, "value");
  desc?.set?.call(el, value);
  el.dispatchEvent(new Event("input", { bubbles: true }));
}

export function plannedWorkingSlice(deps: {
  pane: Pick<SlicePane, "workingNoteId" | "includeMode" | "includeHeading" | "includeOffset" | "workingNoteTitle">;
  articleId: string | null;
  articleBody?: string | null;
  articleTitle: string | null;
  resolveIncludeSlice: (input: SliceInput) => SliceResult;
  articleNeedsIncludeSlice: (body: string | null | undefined, cap?: number) => boolean;
  WORKING_NOTE_CHAR_CAP: number;
}): SliceResult | null {
  const {
    pane,
    articleId,
    articleBody,
    articleTitle,
    resolveIncludeSlice,
    articleNeedsIncludeSlice,
    WORKING_NOTE_CHAR_CAP,
  } = deps;
  if (!pane.workingNoteId) return null;
  const body = pane.workingNoteId === articleId ? articleBody || "" : "";
  if (!body) return null;
  const over = articleNeedsIncludeSlice(body, WORKING_NOTE_CHAR_CAP);
  const mode: IncludeMode =
    pane.includeMode && pane.includeMode !== "auto" ? pane.includeMode : over ? "chunk" : "auto";
  return resolveIncludeSlice({
    body,
    mode,
    heading: pane.includeHeading,
    offset: pane.includeOffset,
    title: pane.workingNoteTitle || articleTitle,
    cap: WORKING_NOTE_CHAR_CAP,
    hardMax: WORKING_NOTE_CHAR_CAP,
  });
}

export function plannedIncludeSlice(deps: {
  pane: Pick<SlicePane, "includeArticle" | "includeMode" | "includeHeading" | "includeOffset">;
  articleId: string | null;
  articleBody?: string | null;
  articleTitle: string | null;
  readerCtx: { selection: string };
  resolveIncludeSlice: (input: SliceInput) => SliceResult;
  articleNeedsIncludeSlice: (body: string | null | undefined, cap?: number) => boolean;
}): SliceResult | null {
  const { pane, articleId, articleBody, articleTitle, readerCtx, resolveIncludeSlice, articleNeedsIncludeSlice } = deps;
  if (!pane.includeArticle || !articleId) return null;
  const mode: IncludeMode = (
    pane.includeMode && pane.includeMode !== "auto"
      ? pane.includeMode
      : articleNeedsIncludeSlice(articleBody)
        ? "chunk"
        : "auto"
  ) as IncludeMode;
  return resolveIncludeSlice({
    body: articleBody || "",
    mode,
    selection: pane.includeMode === "selection" ? readerCtx.selection : undefined,
    heading: pane.includeHeading,
    offset: pane.includeOffset,
    title: articleTitle,
  });
}
