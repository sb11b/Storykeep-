"use client";

import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/sonner";

export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      <div className="flex h-full min-h-0 flex-1 flex-col overflow-hidden">{children}</div>
      <Toaster position="bottom-right" />
    </ThemeProvider>
  );
}
