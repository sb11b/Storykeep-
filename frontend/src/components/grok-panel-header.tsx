"use client";

import { Lock, Maximize2, Pencil, Plus, Sparkles, X } from "lucide-react";
import { GrokRowMenu } from "@/components/grok-row-menu";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MAX_PANES } from "@/lib/useGrokPanels";

type GrokPanelHeaderProps = {
  focusedPaneDisplayName: string;
  subtitle: string;
  fullscreen: boolean;
  locked: boolean;
  panesLength: number;
  persist: boolean;
  messageCryptoEnabled: boolean;
  renamingPaneId: string | null;
  focusedPaneId: string;
  paneRenameDraft: string;
  setPaneRenameDraft: (value: string) => void;
  paneRenameInputRef: React.RefObject<HTMLInputElement | null>;
  startPaneRename: (paneId: string) => void;
  commitPaneRename: (paneId: string) => void;
  cancelPaneRename: () => void;
  addPane: (locked: boolean) => void;
  exitFullscreen: () => void;
  toggleFullscreen: () => void;
  closePanel: () => void;
  setShowCryptoSetup: (show: boolean) => void;
  onPanelDragStart: (event: React.PointerEvent) => void;
};

export function GrokPanelHeader({
  focusedPaneDisplayName,
  subtitle,
  fullscreen,
  locked,
  panesLength,
  persist,
  messageCryptoEnabled,
  renamingPaneId,
  focusedPaneId,
  paneRenameDraft,
  setPaneRenameDraft,
  paneRenameInputRef,
  startPaneRename,
  commitPaneRename,
  cancelPaneRename,
  addPane,
  exitFullscreen,
  toggleFullscreen,
  closePanel,
  setShowCryptoSetup,
  onPanelDragStart,
}: GrokPanelHeaderProps) {
  const headerClass = fullscreen ? "cursor-default" : "cursor-grab active:cursor-grabbing";

  return (
    <div
      className={cn(
        "flex shrink-0 items-center gap-2 border-b px-3 py-2",
        headerClass,
      )}
      onPointerDown={(event) => {
        if (fullscreen) return;
        if ((event.target as HTMLElement).closest("button, [data-resize]")) return;
        onPanelDragStart(event);
      }}
    >
      <Sparkles className="size-4 text-primary" />
      <div className="min-w-0 flex-1">
        {renamingPaneId === focusedPaneId ? (
          <Input
            ref={paneRenameInputRef}
            value={paneRenameDraft}
            className="h-7 max-w-[14rem] px-2 text-sm"
            aria-label="Rename pane"
            onChange={(event) => setPaneRenameDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") {
                event.preventDefault();
                void commitPaneRename(focusedPaneId);
              }
              if (event.key === "Escape") {
                event.preventDefault();
                cancelPaneRename();
              }
            }}
            onBlur={() => void commitPaneRename(focusedPaneId)}
          />
        ) : (
          <button
            type="button"
            className="truncate text-left text-sm font-medium leading-none hover:underline"
            title="Rename pane"
            onClick={() => startPaneRename(focusedPaneId)}
          >
            {focusedPaneDisplayName}
          </button>
        )}
        <p className="truncate text-[11px] text-muted-foreground">
          {fullscreen ? `${panesLength} pane${panesLength === 1 ? "" : "s"}` : subtitle}
        </p>
      </div>
      {renamingPaneId !== focusedPaneId ? (
        <GrokRowMenu
          label={focusedPaneDisplayName}
          items={[
            {
              key: "rename-pane",
              label: "Rename pane",
              icon: <Pencil className="size-3.5" />,
              onSelect: () => startPaneRename(focusedPaneId),
            },
            ...(persist && !messageCryptoEnabled
              ? [
                  {
                    key: "encrypt-at-rest",
                    label: "Encrypt messages at rest",
                    icon: <Lock className="size-3.5" />,
                    onSelect: () => setShowCryptoSetup(true),
                  },
                ]
              : []),
          ]}
        />
      ) : null}
      {fullscreen && !locked && panesLength < MAX_PANES ? (
        <Button size="sm" variant="outline" className="h-7 gap-1 px-2 text-xs" onClick={() => addPane(locked)}>
          <Plus className="size-3.5" />
          Add pane
        </Button>
      ) : null}
      {fullscreen ? (
        <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={exitFullscreen}>
          Exit full screen
        </Button>
      ) : (
        <Button size="icon-xs" variant="ghost" onClick={toggleFullscreen} aria-label="Full screen" title="Full screen (f)">
          <Maximize2 className="size-3.5" />
        </Button>
      )}
      <Button size="icon-xs" variant="ghost" onClick={closePanel} aria-label="Close chat">
        <X className="size-3.5" />
      </Button>
    </div>
  );
}

// Inline cn to avoid extra import churn; matches @/lib/utils cn
function cn(...classes: (string | false | undefined | null)[]): string {
  return classes.filter(Boolean).join(" ");
}
