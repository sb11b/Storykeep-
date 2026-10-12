"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { Update } from "@tauri-apps/plugin-updater";
import {
  INITIAL_UPDATE_STATE,
  checkForUpdate,
  installUpdate,
  shouldShowUpdateBanner,
  type UpdateState,
} from "@/lib/auto-update";
import { Button } from "@/components/ui/button";

/**
 * Startup update check + dismissible banner for the packaged desktop app.
 *
 * On mount (and only in the packaged window — `checkForUpdate` guards on
 * the Tauri runtime itself) the manifest is fetched fire-and-forget: a
 * slow or dead endpoint never blocks startup, and any failure stays
 * invisible. When a newer version exists, a thin bar at the bottom of the
 * window offers an explicit "Install & restart" button and a dismiss —
 * NOTHING downloads or installs without that click. Dismissing hides the
 * banner for the session; the next launch checks again.
 */
export function UpdateBanner() {
  const [state, setState] = useState<UpdateState>(INITIAL_UPDATE_STATE);
  const [update, setUpdate] = useState<Update | null>(null);
  const checkedRef = useRef(false);

  const runCheck = useCallback(async () => {
    setState((s) => (s.status === "idle" ? { ...s, status: "checking" } : s));
    const info = await checkForUpdate();
    if (!info) {
      // No update, not the desktop app, or any silent failure — back to
      // idle so the banner stays hidden.
      setState((s) => (s.status === "checking" ? { ...s, status: "idle" } : s));
      return;
    }
    setUpdate(info.update);
    setState((s) => ({ ...s, status: "available", version: info.version }));
  }, []);

  useEffect(() => {
    // Once per mount. The check is async and never awaited by the render
    // path; `checkForUpdate` is a complete no-op outside the packaged
    // window, so the browser app never fires a request.
    if (checkedRef.current) return;
    checkedRef.current = true;
    void runCheck();
  }, [runCheck]);

  const onInstall = useCallback(() => {
    if (!update) return;
    setState((s) => ({ ...s, status: "downloading" }));
    // Passive mode: the plugin shows its own download progress and
    // relaunches the app once the new binary is staged. A failure drops
    // back to "available" so the banner stays actionable — never an
    // error dialog for a convenience feature.
    void installUpdate(update).catch(() => {
      setState((s) => ({ ...s, status: "available" }));
    });
  }, [update]);

  const onDismiss = useCallback(() => {
    setState((s) => ({ ...s, dismissed: true }));
  }, []);

  if (!shouldShowUpdateBanner(state)) return null;

  const downloading = state.status === "downloading";

  return (
    <div
      role="status"
      data-testid="update-banner"
      className="fixed bottom-0 left-0 right-0 z-50 flex items-center justify-between gap-4 border-t border-border bg-card px-4 py-2 text-sm"
    >
      <span className="text-muted-foreground">
        {downloading
          ? `Downloading StoryKeep ${state.version} — the app will restart when it's ready.`
          : `StoryKeep ${state.version} is ready to install.`}
      </span>
      {!downloading && (
        <span className="flex shrink-0 items-center gap-2">
          <Button size="sm" onClick={onInstall}>
            Install &amp; restart
          </Button>
          <Button size="sm" variant="ghost" onClick={onDismiss}>
            Later
          </Button>
        </span>
      )}
    </div>
  );
}
