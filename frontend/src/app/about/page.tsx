"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, type HealthInfo } from "@/lib/api";

const BAKED_SHA = process.env.NEXT_PUBLIC_BUILD_SHA?.trim() || "";

export default function AboutPage() {
  const [health, setHealth] = useState<HealthInfo | null>(null);

  useEffect(() => {
    api
      .health()
      .then(setHealth)
      .catch(() => {
        setHealth(null);
      });
  }, []);

  const build = health?.build || BAKED_SHA || "unknown";
  const builtAt = health?.built_at || "";

  return (
    <main className="mx-auto flex min-h-dvh max-w-lg flex-col justify-center gap-4 px-6 py-10">
      <h1 className="font-[family-name:var(--font-serif)] text-4xl tracking-tight">StoryKeep</h1>
      <p className="text-sm text-muted-foreground">
        A personal RSS reader and article archive. Sign in to open your library. Chat stays behind a
        signed-in Junior pane.
      </p>
      <p className="text-sm" title="Deployed build">
        Build <strong>{build}</strong>
        {builtAt ? <span className="text-muted-foreground"> · {builtAt}</span> : null}
      </p>
      <p>
        <Link href="/login" className="text-sm underline underline-offset-4">
          Sign in
        </Link>
      </p>
    </main>
  );
}
