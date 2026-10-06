"use client";

import type { CSSProperties } from "react";
import { GrokPane as GrokPaneComponent } from "@/components/grok-pane";
import type { GrokPaneState } from "@/components/grok-pane";
import type { CustomNoteShelf, FilingDestination } from "@/lib/custom-note-shelves";
import type { TtsVoice } from "@/lib/types";

function paneGridStyle(count: number): CSSProperties {
  if (count <= 1) return { gridTemplateColumns: "1fr", gridTemplateRows: "1fr" };
  if (count === 2) return { gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr" };
  return { gridTemplateColumns: "1fr 1fr", gridTemplateRows: "1fr 1fr" };
}

function paneCellStyle(count: number, index: number): CSSProperties | undefined {
  if (count === 3 && index === 2) return { gridColumn: "1 / span 2" };
  return undefined;
}

type GrokPanelGridProps = {
  panes: GrokPaneState[];
  focusedPaneId: string;
  compact: true;
  articleId: string | null;
  articleTitle: string | null;
  articleGuid?: string | null;
  sourceRef?: string | null;
  articleBody?: string | null;
  enabled: boolean;
  ttsEnabled: boolean;
  sttEnabled: boolean;
  locked: boolean;
  persist: boolean;
  messageCryptoEnabled: boolean;
  panelOpen: boolean;
  ttsVoices: TtsVoice[];
  defaultTtsVoiceId: string;
  customShelves: CustomNoteShelf[];
  chatModels: string[];
  onSavedNote: (noteId?: string, destination?: FilingDestination, folderId?: string | null) => Promise<void>;
  onStopArticleListen?: () => void;
  onOpenArticle?: (id: string) => void;
  onActivateListen: (stop: (() => void) | null) => void;
  onHistoryChanged: () => void;
  onFocusPane: (id: string) => void;
  onUpdatePane: (id: string, updater: (pane: GrokPaneState) => GrokPaneState) => void;
  onRemovePane: (id: string) => void;
  onCreateNoteShelf: () => Promise<void>;
  onOpenRemainderChat: (remainder: string) => boolean;
  paneRenameProps: (paneId: string) => {
    renamingLabel: boolean;
    renameDraft: string;
    onStartRename: () => void;
    onRenameDraftChange: (value: string) => void;
    onCommitRename: () => void;
    onCancelRename: () => void;
  };
};

export function GrokPanelGrid(props: GrokPanelGridProps) {
  const {
    panes,
    focusedPaneId,
    articleId,
    articleTitle,
    articleGuid,
    sourceRef,
    articleBody,
    enabled,
    ttsEnabled,
    sttEnabled,
    locked,
    persist,
    messageCryptoEnabled,
    panelOpen,
    ttsVoices,
    defaultTtsVoiceId,
    customShelves,
    chatModels,
    onSavedNote,
    onStopArticleListen,
    onOpenArticle,
    onActivateListen,
    onHistoryChanged,
    onFocusPane,
    onUpdatePane,
    onRemovePane,
    onCreateNoteShelf,
    onOpenRemainderChat,
    paneRenameProps,
  } = props;

  return (
    <div
      className="grid min-h-0 min-w-0 flex-1 gap-px overflow-hidden bg-border"
      style={paneGridStyle(panes.length)}
    >
      {panes.map((pane, index) => (
        <div
          key={pane.id}
          className="min-h-0 min-w-0 overflow-hidden bg-popover"
          style={paneCellStyle(panes.length, index)}
        >
          <GrokPaneComponent
            pane={pane}
            label={pane.displayName}
            compact
            focused={pane.id === focusedPaneId}
            canRemove={panes.length > 1}
            {...paneRenameProps(pane.id)}
            articleId={articleId}
            articleTitle={articleTitle}
            articleGuid={articleGuid}
            sourceRef={sourceRef}
            articleBody={articleBody}
            enabled={enabled}
            ttsEnabled={ttsEnabled}
            sttEnabled={sttEnabled}
            locked={locked}
            onFocus={() => onFocusPane(pane.id)}
            onUpdate={(updater) => onUpdatePane(pane.id, updater)}
            onRemove={() => onRemovePane(pane.id)}
            onSavedNote={onSavedNote}
            onActivateListen={onActivateListen}
            onStopArticleListen={onStopArticleListen}
            onHistoryChanged={onHistoryChanged}
            chatModels={chatModels}
            persist={persist}
            messageCryptoEnabled={messageCryptoEnabled}
            panelOpen={panelOpen}
            ttsVoices={ttsVoices}
            defaultTtsVoiceId={defaultTtsVoiceId}
            customShelves={customShelves}
            onCreateNoteShelf={onCreateNoteShelf}
            onOpenArticle={onOpenArticle}
            onOpenRemainderChat={onOpenRemainderChat}
          />
        </div>
      ))}
    </div>
  );
}

type GrokSinglePaneProps = {
  pane: GrokPaneState;
  articleId: string | null;
  articleTitle: string | null;
  articleGuid?: string | null;
  sourceRef?: string | null;
  articleBody?: string | null;
  enabled: boolean;
  ttsEnabled: boolean;
  sttEnabled: boolean;
  locked: boolean;
  persist: boolean;
  messageCryptoEnabled: boolean;
  panelOpen: boolean;
  ttsVoices: TtsVoice[];
  defaultTtsVoiceId: string;
  customShelves: CustomNoteShelf[];
  chatModels: string[];
  onSavedNote: (noteId?: string, destination?: FilingDestination, folderId?: string | null) => Promise<void>;
  onStopArticleListen?: () => void;
  onOpenArticle?: (id: string) => void;
  onActivateListen: (stop: (() => void) | null) => void;
  onHistoryChanged: () => void;
  onFocusPane: (id: string) => void;
  onUpdatePane: (id: string, updater: (pane: GrokPaneState) => GrokPaneState) => void;
  onCreateNoteShelf: () => Promise<void>;
  onOpenRemainderChat: (remainder: string) => boolean;
  paneRenameProps: (paneId: string) => {
    renamingLabel: boolean;
    renameDraft: string;
    onStartRename: () => void;
    onRenameDraftChange: (value: string) => void;
    onCommitRename: () => void;
    onCancelRename: () => void;
  };
};

export function GrokSinglePane(props: GrokSinglePaneProps) {
  const {
    pane,
    articleId,
    articleTitle,
    articleGuid,
    sourceRef,
    articleBody,
    enabled,
    ttsEnabled,
    sttEnabled,
    locked,
    persist,
    messageCryptoEnabled,
    panelOpen,
    ttsVoices,
    defaultTtsVoiceId,
    customShelves,
    chatModels,
    onSavedNote,
    onStopArticleListen,
    onOpenArticle,
    onActivateListen,
    onHistoryChanged,
    onFocusPane,
    onUpdatePane,
    onCreateNoteShelf,
    onOpenRemainderChat,
    paneRenameProps,
  } = props;

  return (
    <div className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
      <GrokPaneComponent
        key={pane.id}
        pane={pane}
        label={pane.displayName}
        {...paneRenameProps(pane.id)}
        articleId={articleId}
        articleTitle={articleTitle}
        articleGuid={articleGuid}
        sourceRef={sourceRef}
        articleBody={articleBody}
        enabled={enabled}
        ttsEnabled={ttsEnabled}
        sttEnabled={sttEnabled}
        locked={locked}
        onFocus={() => onFocusPane(pane.id)}
        onUpdate={(updater) => onUpdatePane(pane.id, updater)}
        onSavedNote={onSavedNote}
        onActivateListen={onActivateListen}
        onStopArticleListen={onStopArticleListen}
        onHistoryChanged={onHistoryChanged}
        chatModels={chatModels}
        persist={persist}
        messageCryptoEnabled={messageCryptoEnabled}
        panelOpen={panelOpen}
        ttsVoices={ttsVoices}
        defaultTtsVoiceId={defaultTtsVoiceId}
        customShelves={customShelves}
        onCreateNoteShelf={onCreateNoteShelf}
        onOpenArticle={onOpenArticle}
        onOpenRemainderChat={onOpenRemainderChat}
      />
    </div>
  );
}
