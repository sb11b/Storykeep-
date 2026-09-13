export type ThreadNoteTurn = {
  role: "user" | "assistant" | string;
  content: string;
};

const TITLE_MAX = 80;

export function saveableThreadTurns(turns: ThreadNoteTurn[]): ThreadNoteTurn[] {
  return turns.filter((turn) => {
    if (turn.role !== "user" && turn.role !== "assistant") return false;
    return Boolean(turn.content.trim());
  });
}

export function threadNoteTitle(opts: {
  conversationTitle?: string | null;
  firstUserLine?: string | null;
  now?: Date;
}): string {
  const renamed = (opts.conversationTitle || "").trim();
  if (renamed && renamed !== "New chat") return renamed.slice(0, TITLE_MAX);
  const line =
    (opts.firstUserLine || "")
      .trim()
      .split("\n")
      .find((item) => item.trim()) || "";
  const compact = line.replace(/^#+\s*/, "").replace(/^["“]+|["”]+$/g, "").slice(0, TITLE_MAX);
  if (compact) return compact;
  const now = opts.now ?? new Date();
  const month = String(now.getMonth() + 1).padStart(2, "0");
  const day = String(now.getDate()).padStart(2, "0");
  return `Junior chat ${now.getFullYear()}-${month}-${day}`;
}

export function threadNoteMarkdown(
  turns: ThreadNoteTurn[],
  opts?: { title?: string; userName?: string; assistantName?: string },
): string {
  const userName = opts?.userName || "Steve";
  const assistantName = opts?.assistantName || "Junior";
  const blocks: string[] = [];
  for (const turn of saveableThreadTurns(turns)) {
    const who = turn.role === "user" ? userName : assistantName;
    blocks.push(`**${who}**\n\n${turn.content.trim()}`);
  }
  const body = blocks.join("\n\n");
  const title = (opts?.title || "").trim();
  if (title) return `# ${title}\n\n${body}`;
  return body;
}
