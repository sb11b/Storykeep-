"use client";

import { Brain, CalendarClock, ChevronLeft, History, LoaderCircle, MessageSquarePlus, Pencil, Pin, Trash2 } from "lucide-react";
import { GrokRowMenu } from "@/components/grok-row-menu";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { grokModelLabel } from "@/lib/grok-model";
import { cn } from "@/lib/utils";
import type { GrokConversation } from "@/lib/types";

type GrokPanelSidebarProps = {
  conversations: GrokConversation[];
  historyLoading: boolean;
  focusedConversationId: string | null;
  renamingId: string | null;
  renameDraft: string;
  setRenameDraft: (value: string) => void;
  renameInputRef: React.RefObject<HTMLInputElement | null>;
  historyListRef: React.RefObject<HTMLDivElement | null>;
  onStartNewChat: () => void;
  onLoadConversation: (id: string) => void;
  onPinConversation: (row: GrokConversation) => void;
  onDeleteConversation: (row: GrokConversation) => void;
  onStartRename: (row: GrokConversation) => void;
  onCommitRename: (conversationId: string) => void;
  onCancelRename: () => void;
  onHide: () => void;
};

export function GrokPanelSidebar({
  conversations,
  historyLoading,
  focusedConversationId,
  renamingId,
  renameDraft,
  setRenameDraft,
  renameInputRef,
  historyListRef,
  onStartNewChat,
  onLoadConversation,
  onPinConversation,
  onDeleteConversation,
  onStartRename,
  onCommitRename,
  onCancelRename,
  onHide,
}: GrokPanelSidebarProps) {
  return (
    <aside className="flex w-44 shrink-0 flex-col overflow-hidden border-r bg-muted/15">
      <div className="flex shrink-0 items-center gap-1 border-b p-1.5">
        <Button
          type="button"
          size="sm"
          variant="ghost"
          className="h-7 shrink-0 gap-0.5 px-1.5 text-[11px]"
          aria-label="Hide Chats"
          aria-expanded={true}
          title="Hide Chats"
          onClick={onHide}
        >
          <ChevronLeft className="size-3.5" />
          Hide
        </Button>
        <Button size="sm" variant="secondary" className="h-7 min-w-0 flex-1 gap-1 px-1.5 text-xs" onClick={onStartNewChat}>
          <MessageSquarePlus className="size-3.5" />
          New chat
        </Button>
      </div>
      <div ref={historyListRef} className="min-h-0 flex-1 overflow-y-auto overscroll-contain p-1">
        {historyLoading ? (
          <p className="flex items-center gap-1 px-2 py-2 text-[11px] text-muted-foreground">
            <LoaderCircle className="size-3 animate-spin" />
            Loading…
          </p>
        ) : conversations.length === 0 ? (
          <p className="px-2 py-2 text-[11px] text-muted-foreground">Past chats appear here.</p>
        ) : (
          conversations.map((row) => {
            const active = focusedConversationId === row.id;
            const renaming = renamingId === row.id;
            return (
              <div key={row.id} className="group flex items-start gap-0.5">
                {renaming ? (
                  <Input
                    ref={renameInputRef}
                    value={renameDraft}
                    className="h-7 min-w-0 flex-1 px-2 text-[11px]"
                    aria-label="Rename chat"
                    onChange={(event) => setRenameDraft(event.target.value)}
                    onKeyDown={(event) => {
                      if (event.key === "Enter") {
                        event.preventDefault();
                        void onCommitRename(row.id);
                      }
                      if (event.key === "Escape") {
                        event.preventDefault();
                        onCancelRename();
                      }
                    }}
                    onBlur={() => void onCommitRename(row.id)}
                  />
                ) : (
                  <button
                    type="button"
                    className={cn(
                      "min-w-0 flex-1 rounded-md px-2 py-1.5 text-left text-[11px] leading-snug hover:bg-accent/60",
                      active && "bg-accent/80 font-medium",
                    )}
                    title={row.title}
                    onClick={() => onLoadConversation(row.id)}
                    onDoubleClick={(event) => {
                      event.preventDefault();
                      onStartRename(row);
                    }}
                  >
                    <span className="line-clamp-2">
                      {row.pinned ? <Pin className="mr-1 inline size-3 fill-current" /> : null}
                      {row.title}
                    </span>
                    <span className="mt-0.5 block truncate text-[10px] text-muted-foreground">
                      {grokModelLabel(row.model || "auto", row.last_model, row.last_reasoning)}
                    </span>
                  </button>
                )}
                {!renaming ? (
                  <Button
                    type="button"
                    size="icon-xs"
                    variant="ghost"
                    className={cn("mt-0.5 shrink-0", row.pinned ? "text-primary" : "text-muted-foreground")}
                    aria-label={row.pinned ? `Unpin ${row.title}` : `Pin ${row.title} to the top`}
                    onClick={() => onPinConversation(row)}
                  >
                    <Pin className={cn("size-3.5", row.pinned && "fill-current")} />
                  </Button>
                ) : null}
                {!renaming ? (
                  <GrokRowMenu
                    label={row.title}
                    className="mt-0.5"
                    items={[
                      {
                        key: "pin",
                        label: row.pinned ? "Unpin from top" : "Pin to top",
                        icon: <Pin className="size-3.5" />,
                        onSelect: () => onPinConversation(row),
                      },
                      {
                        key: "rename",
                        label: "Rename thread",
                        icon: <Pencil className="size-3.5" />,
                        onSelect: () => onStartRename(row),
                      },
                      {
                        key: "delete",
                        label: "Delete thread",
                        icon: <Trash2 className="size-3.5" />,
                        destructive: true,
                        onSelect: () => onDeleteConversation(row),
                      },
                    ]}
                  />
                ) : null}
              </div>
            );
          })
        )}
      </div>
    </aside>
  );
}

export function GrokHiddenStrip({
  showChats,
  ownerRails,
  showJobs,
  showMemory,
  onStartNewChat,
  onShowHistory,
  onShowJobs,
  onShowMemory,
}: {
  showChats: boolean;
  ownerRails: boolean;
  showJobs: boolean;
  showMemory: boolean;
  onStartNewChat: () => void;
  onShowHistory: () => void;
  onShowJobs: () => void;
  onShowMemory: () => void;
}) {
  if (showChats && (!ownerRails || showJobs) && (!ownerRails || showMemory)) return null;
  const collapsedIconBtn = "h-8 w-8 shrink-0 text-muted-foreground hover:text-foreground";
  return (
    <aside className="flex w-11 shrink-0 flex-col items-center gap-1 border-r bg-muted/15 py-1">
      {!showChats ? (
        <>
          <Button
            type="button"
            size="icon-xs"
            variant="ghost"
            className={collapsedIconBtn}
            aria-label="New chat"
            title="New chat"
            onClick={onStartNewChat}
          >
            <MessageSquarePlus className="size-3.5" />
          </Button>
          <Button
            type="button"
            size="icon-xs"
            variant="ghost"
            className={collapsedIconBtn}
            aria-label="Show Chats"
            aria-expanded={false}
            title="Show Chats"
            onClick={onShowHistory}
          >
            <History className="size-3.5" />
          </Button>
        </>
      ) : null}
      {ownerRails && !showJobs ? (
        <Button
          type="button"
          size="icon-xs"
          variant="ghost"
          className={collapsedIconBtn}
          aria-label="Show Jobs"
          aria-expanded={false}
          title="Show Jobs"
          onClick={onShowJobs}
        >
          <CalendarClock className="size-3.5" />
        </Button>
      ) : null}
      {ownerRails && !showMemory ? (
        <Button
          type="button"
          size="icon-xs"
          variant="ghost"
          className={collapsedIconBtn}
          aria-label="Show Memory"
          aria-expanded={false}
          title="Show Memory"
          onClick={onShowMemory}
        >
          <Brain className="size-3.5" />
        </Button>
      ) : null}
    </aside>
  );
}


