"use client";

import type { ReactNode } from "react";
import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/sonner";
import { DictationProvider } from "@/components/dictation";

export function Providers({ children }: { children: ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <DictationProvider>
        <div className="flex h-full min-h-0 min-w-0 flex-col overflow-hidden">{children}</div>
        <Toaster position="bottom-left" />
      </DictationProvider>
    </ThemeProvider>
  );
}
