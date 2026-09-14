import type { MouseEvent } from "react";
import { toast } from "sonner";

/** Copy / Run buttons inside `.sk-code` blocks. Copy stays on the fence; Run is optional. */
export function onCodeCopyClick(event: MouseEvent<HTMLElement>, onRun?: (code: string) => void) {
  const run = (event.target as HTMLElement).closest<HTMLButtonElement>("[data-run]");
  if (run) {
    const pre = run.closest("pre.sk-code");
    const code = pre?.querySelector("code");
    if (!code) return;
    event.preventDefault();
    event.stopPropagation();
    onRun?.(code.textContent ?? "");
    return;
  }
  const button = (event.target as HTMLElement).closest<HTMLButtonElement>("[data-copy]");
  if (!button) return;
  const pre = button.closest("pre.sk-code");
  const code = pre?.querySelector("code");
  if (!code) return;
  event.preventDefault();
  event.stopPropagation();
  const text = code.textContent ?? "";
  void navigator.clipboard.writeText(text).then(
    () => toast.success("Copied to clipboard"),
    () => toast.error("Could not copy"),
  );
}
