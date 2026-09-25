import { isSilentEmptyChatDetail } from "./grok-chat-error";

/** Use the row Postgres already saved when the live stream painted no words. */
export function savedReplyFillsEmptyBubble(localContent: string, savedText: string): boolean {
  const local = (localContent || "").trim();
  if (local && !isSilentEmptyChatDetail(local)) return false;
  const saved = (savedText || "").trim();
  return Boolean(saved) && !isSilentEmptyChatDetail(saved);
}
