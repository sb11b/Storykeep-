export function grokModelLabel(choice: string, lastModel?: string | null): string {
  if (choice === "auto") return lastModel ? `Auto · ${lastModel}` : "Auto";
  return choice;
}
