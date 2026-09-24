/** STS conversation-mode rearm rules. Keep mic listening after a turn or a failed take. */

export const STS_REARM_AFTER_TURN_MS = 120;
export const STS_REARM_DEFER_MS = 50;
export const STS_REARM_DEFER_MAX = 10;

export type StsListenPhase = "idle" | "loading" | "playing" | "paused";
export type StsMicPhase = "idle" | "listening" | "transcribing";

export type StsRearmGate = {
  stsModeOn: boolean;
  ttsPaused: boolean;
  sttPhase: StsMicPhase;
  busy: boolean;
  inFlight: boolean;
  listenPhase: StsListenPhase;
};

/** Parent pane may start the next STS take only when Castor is idle and the turn is done. */
export function shouldRearmSts(gate: StsRearmGate): boolean {
  if (!gate.stsModeOn || gate.ttsPaused) return false;
  if (gate.sttPhase !== "idle") return false;
  if (gate.busy || gate.inFlight) return false;
  if (gate.listenPhase === "loading" || gate.listenPhase === "playing" || gate.listenPhase === "paused") {
    return false;
  }
  return true;
}

/** After a mic take, rearm immediately unless a chat turn was submitted (Castor / error path rearms). */
export function shouldRearmStsAfterMicTake(input: { stsModeOn: boolean; submittedTurn: boolean }): boolean {
  return input.stsModeOn && !input.submittedTurn;
}

/** Retry a skipped rearm while transcribe/processing flags drain. */
export function nextStsRearmDeferMs(tries: number): number | null {
  if (tries >= STS_REARM_DEFER_MAX) return null;
  return STS_REARM_DEFER_MS;
}
