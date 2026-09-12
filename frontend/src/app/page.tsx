"use client";

import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { LibraryApp } from "@/components/library-app";
import { ApiError, api } from "@/lib/api";
import type { User } from "@/lib/types";

export default function HomePage() {
  const router = useRouter();
  const pathname = usePathname();
  const [user, setUser] = useState<User | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (pathname !== "/") return;
    api
      .me()
      .then(setUser)
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) {
          router.replace("/login");
          return;
        }
        setError(err instanceof Error ? err.message : "Could not reach Storykeep");
      });
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

  return <LibraryApp user={user} />;
}
