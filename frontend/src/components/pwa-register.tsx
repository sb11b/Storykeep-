"use client";

import { useEffect, useState } from "react";

/**
 * Registers the library-aware service worker (production only) and renders a
 * small, honest offline indicator: when the network is down, the app shows the
 * cached shell and last-seen Junior library (stale-while-revalidate). No data
 * is fabricated — a thin bar simply says what the user is looking at.
 */
export function PwaRegister() {
  const [offline, setOffline] = useState(false);

  useEffect(() => {
    if (process.env.NODE_ENV !== "production") return;
    if (!("serviceWorker" in navigator)) return;
    const onLoad = () => {
      navigator.serviceWorker.register("/sw.js", { scope: "/" }).catch(() => {
        // Registration failure is non-fatal: the app works online without it.
      });
    };
    window.addEventListener("load", onLoad);
    return () => window.removeEventListener("load", onLoad);
  }, []);

  useEffect(() => {
    const update = () => setOffline(!navigator.onLine);
    update();
    window.addEventListener("online", update);
    window.addEventListener("offline", update);
    return () => {
      window.removeEventListener("online", update);
      window.removeEventListener("offline", update);
    };
  }, []);

  if (!offline) return null;

  return (
    <div
      role="status"
      data-testid="offline-indicator"
      className="fixed bottom-0 left-0 right-0 z-50 border-t border-border bg-card px-4 py-2 text-center text-xs text-muted-foreground"
    >
      Offline — showing cached pages and your last-seen library. Edits and
      sync will fail until you reconnect.
    </div>
  );
}
