import { isSilentEmptyChatDetail } from "./grok-chat-error";
import { EMPTY_REPLY_BODY } from "./grok-pane-name";

/** Keep the typed line in the composer when the turn ends on the silent fallback. */
export function restoreDraftAfterSilent(currentDraft: string, sent: string, reply: string): string {
  if ((currentDraft || "").trim()) return currentDraft;
  const body = (reply || "").trim();
  if (!body) return currentDraft;
  if (body !== EMPTY_REPLY_BODY && !isSilentEmptyChatDetail(body)) return currentDraft;
  return (sent || "").trim();
}
