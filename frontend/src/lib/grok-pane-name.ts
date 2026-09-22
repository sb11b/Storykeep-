/** Default chat pane name. Steve can rename a pane later. */
export const DEFAULT_PANE_NAME = "Junior";

/** Labels the UI shipped with before Junior; still scrubbed from preferences. */
const LEGACY_DEFAULT_NAMES = ["Grok", "Grok panel", "Larry", "Larry (the asparagus)"];

export function defaultGrokPaneName(index: number) {
  return index === 0 ? DEFAULT_PANE_NAME : `${DEFAULT_PANE_NAME} ${index + 1}`;
}

/** True for any name that is a default label rather than something Steve typed. */
export function isDefaultPaneName(name: string, index: number): boolean {
  const trimmed = name.trim();
  if (!trimmed) return true;
  if (trimmed === DEFAULT_PANE_NAME) return true;
  if (trimmed === defaultGrokPaneName(index)) return true;
  return LEGACY_DEFAULT_NAMES.some(
    (legacy) => trimmed === legacy || trimmed === `${legacy} ${index + 1}`,
  );
}

export type ChatTurnStatus = "queued" | "thinking" | "writing" | "done" | "error";

/** Server/stream aliases plus the turn enum. `working` means Thinking. */
export type ChatStatusKind =
  | ChatTurnStatus
  | "working"
  | "generating"
  | "searching"
  | "starting_agent"
  | "deploying";

export const NO_REPLY_TOAST = "No reply — retry";

export function normalizeTurnStatus(kind: string | null | undefined): ChatTurnStatus | null {
  if (!kind) return null;
  if (kind === "queued") return "queued";
  if (
    kind === "thinking" ||
    kind === "working" ||
    kind === "searching" ||
    kind === "starting_agent" ||
    kind === "deploying"
  ) {
    return "thinking";
  }
  if (kind === "writing" || kind === "generating") return "writing";
  if (kind === "done") return "done";
  if (kind === "error") return "error";
  return null;
}

export function chatStatusLine(name: string, kind: ChatStatusKind): string {
  const who = name.trim() || DEFAULT_PANE_NAME;
  const turn = normalizeTurnStatus(kind);
  if (turn === "error") return "Error";
  if (kind === "searching") return "Searching…";
  if (kind === "starting_agent") return "Starting Cloud Agent…";
  if (kind === "deploying") return "Deploying Storykeep…";
  if (kind === "generating") return `${who} is generating…`;
  if (kind === "working") return `${who} is working…`;
  if (turn === "queued" || turn === "thinking") return `${who} is thinking…`;
  if (turn === "writing") return `${who} is writing…`;
  return "";
}

export function closeAssistantTurn(
  content: string,
  opts?: { fileCount?: number; aborted?: boolean },
): {
  turnStatus: ChatTurnStatus;
  failed: boolean;
  waiting: false;
  error: string | null;
} {
  const hasBody = Boolean(content.trim()) || (opts?.fileCount ?? 0) > 0;
  if (hasBody && !opts?.aborted) {
    return { turnStatus: "done", failed: false, waiting: false, error: null };
  }
  return { turnStatus: "error", failed: true, waiting: false, error: NO_REPLY_TOAST };
}
