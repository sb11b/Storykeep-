import type { MouseEvent } from "react";
import { toast } from "sonner";

/** Copy button inside `.sk-code` blocks — copies code text only. */
export function onCodeCopyClick(event: MouseEvent<HTMLElement>) {
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
