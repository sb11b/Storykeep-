import { asFilingDestination } from "@/lib/destinations";

const SCHOOL_PANE = /\b(?:school(?:work)?|homework|dat|mat|ids|class)\b/i;
const DEFAULT_PANE = /^junior(?:\s+\d+)?$/i;

export function shelfForFinishedChat(paneName: string, selectedShelf: string): string {
  const shelf = asFilingDestination(selectedShelf, "notes");
  if (shelf !== "notes") return shelf;
  if (SCHOOL_PANE.test(paneName || "")) return "schoolwork";
  return shelf;
}

export function folderNameForFinishedChat(paneName: string): string {
  const name = (paneName || "").trim().replace(/\s+/g, " ");
  if (!name || DEFAULT_PANE.test(name)) return "Junior chats";
  return name.slice(0, 80);
}
