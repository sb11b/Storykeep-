import type { MouseEvent } from "react";
import { toast } from "sonner";
import { onCodeCopyClick } from "@/lib/code-copy";

const WIKILINK_TARGET_RE = /\[\[([^\]|#]+)(?:\|[^\]]+)?\]\]/g;

export function extractWikilinkTargets(markdown: string): string[] {
  const seen = new Set<string>();
  const ordered: string[] = [];
  for (const match of (markdown || "").matchAll(WIKILINK_TARGET_RE)) {
    const target = (match[1] || "").trim();
    if (!target || seen.has(target)) continue;
    seen.add(target);
    ordered.push(target);
  }
  return ordered;
}

export type WikilinkResolution = { id: string; title: string };

export type WikilinkResolver = (target: string) => WikilinkResolution | null | undefined;

export type WikilinkClickContext = {
  shelf: string | null;
  folderId: string | null;
  onOpenNote: (id: string) => void;
  onCreateNote: (title: string, shelf: string | null, folderId: string | null) => Promise<string | null>;
  resolveTitle: (title: string, shelf: string | null) => Promise<WikilinkResolution | null>;
};

async function handleMissingWikilink(target: string, ctx: WikilinkClickContext) {
  const resolved = await ctx.resolveTitle(target, ctx.shelf);
  if (resolved) {
    ctx.onOpenNote(resolved.id);
    return;
  }
  toast(`No note titled “${target}”`, {
    action: {
      label: "Create note with this title",
      onClick: () => {
        void ctx.onCreateNote(target, ctx.shelf, ctx.folderId).then((id) => {
          if (id) ctx.onOpenNote(id);
        });
      },
    },
  });
}

/** Reader / preview click handler for wikilinks and code-copy buttons. */
export function onReaderBodyClick(event: MouseEvent<HTMLElement>, ctx: WikilinkClickContext) {
  const wikilink = (event.target as HTMLElement).closest<HTMLButtonElement>(".wikilink");
  if (wikilink) {
    event.preventDefault();
    event.stopPropagation();
    const id = wikilink.dataset.wikilinkId;
    if (id) {
      ctx.onOpenNote(id);
      return;
    }
    const target = wikilink.dataset.wikilinkTarget;
    if (target) void handleMissingWikilink(target, ctx);
    return;
  }
  onCodeCopyClick(event);
}

export function wikilinkQueryAtCaret(
  source: string,
  caret: number,
): { query: string; replaceFrom: number; replaceTo: number } | null {
  const before = source.slice(0, caret);
  const open = before.lastIndexOf("[[");
  if (open === -1) return null;
  const afterOpen = before.slice(open + 2);
  if (afterOpen.includes("]]") || /[\n\r]/.test(afterOpen) || afterOpen.includes("|")) return null;
  return { query: afterOpen, replaceFrom: open + 2, replaceTo: caret };
}
