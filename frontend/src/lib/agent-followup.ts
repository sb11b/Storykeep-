/** True while a Cloud Agent was started in this thread and the finish note is not in yet. */

export function agentFollowUpPending(messages: { role: string; content: string }[]): boolean {
  let pending = false;
  for (const message of messages) {
    if (message.role !== "assistant") continue;
    const text = message.content || "";
    if (text.includes("Cloud Agent update")) pending = false;
    else if (text.includes("Cursor Cloud Agent started")) pending = true;
  }
  return pending;
}
