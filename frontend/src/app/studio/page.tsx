"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { StudioApp } from "@/components/studio-app";
import { applyAppearanceFromUser } from "@/lib/appearance";
import { ApiError, api } from "@/lib/api";
import { normalizeUserProfile } from "@/lib/user-profile";

export default function StudioPage() {
  const router = useRouter();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api
      .me()
      .then((user) => {
        if (cancelled) return;
        applyAppearanceFromUser(normalizeUserProfile(user));
        setReady(true);
      })
      .catch((err) => {
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
          return;
        }
        setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [router]);

  if (!ready) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-muted-foreground">
        Opening Grok Studio…
      </div>
    );
  }

  return (
    <div className="flex h-screen min-h-0 flex-col overflow-hidden">
      <StudioApp />
    </div>
  );
}
