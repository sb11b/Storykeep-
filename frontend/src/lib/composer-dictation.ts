/**
 * Visibility rule for the STT dictation mic in the Junior composer.
 *
 * The mic was collateral removal when the STS (Talk) button was deleted. It
 * lives next to the Talk button in grok-pane.tsx and dictates into the
 * composer textarea — but dictation and Talk both own the microphone, so the
 * mic must never be usable while a Talk session is live (or while a reply is
 * generating). Kept as a pure predicate so the rule is unit-testable without
 * a DOM renderer.
 */

/** Conversation-mode status, mirrored from use-conversation-voice. */
export type DictationMicStatus = "idle" | "connecting" | "listening" | "speaking" | "thinking";

export interface DictationMicGateInput {
  /** Non-null when the DictationProvider is mounted above the composer. */
  dictationAvailable: boolean;
  /** Demo/locked account — no chat, dictation, or Listen. */
  locked: boolean;
  conversationStatus: DictationMicStatus;
  busy: boolean;
  aborting: boolean;
}

/** True when the composer should render the dictation mic button. */
export function showDictationMic(input: DictationMicGateInput): boolean {
  return (
    input.dictationAvailable &&
    !input.locked &&
    input.conversationStatus === "idle" &&
    !input.busy &&
    !input.aborting
  );
}
