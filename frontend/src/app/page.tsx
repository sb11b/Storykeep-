"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LibraryApp } from "@/components/library-app";
import { applyAppearanceFromUser } from "@/lib/appearance";
import { ApiError, api } from "@/lib/api";
import { isPublicAppPath } from "@/lib/public-routes";
import type { Profile, User } from "@/lib/types";
import { mergeUserProfile, normalizeUserProfile } from "@/lib/user-profile";

const AUTH_WAIT_MS = 8000;

export default function HomePage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (isPublicAppPath(pathname)) return;
    let cancelled = false;
    const timer = window.setTimeout(() => {
      if (!cancelled) router.replace("/login");
    }, AUTH_WAIT_MS);
    api
      .me()
      .then((next) => {
        if (cancelled) return;
        window.clearTimeout(timer);
        const user = normalizeUserProfile(next);
        applyAppearanceFromUser(user);
        setUser(user);
      })
      .catch((err) => {
        window.clearTimeout(timer);
        if (cancelled) return;
        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
          return;
        }
        setError(err instanceof Error ? err.message : "Could not reach Storykeep");
      });
    return () => {
      cancelled = true;
      window.clearTimeout(timer);
    };
  }, [router, pathname]);

  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center px-6">
        <div className="max-w-md text-center">
          <p className="font-[family-name:var(--font-serif)] text-2xl">The archive is unreachable</p>
          <p className="text-sm text-muted-foreground mt-2">{error}</p>
        </div>
      </div>
    );
  }

  if (!user) {
    return (
      <div className="min-h-screen flex items-center justify-center text-sm text-muted-foreground">
        Opening your library…
      </div>
    );
  }

  return (
    <LibraryApp
      user={user}
      onUserChange={(patch) => {
        setUser((current) => {
          if (!current) return patch as User;
          const next = mergeUserProfile(current, patch as Profile);
          applyAppearanceFromUser(next);
          return next;
        });
      }}
    />
  );
}
