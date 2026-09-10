"use client";

import { useTheme } from "next-themes";
import { Toaster as Sonner, type ToasterProps } from "sonner";
import {
  CircleCheckIcon,
  InfoIcon,
  TriangleAlertIcon,
  OctagonXIcon,
  Loader2Icon,
} from "lucide-react";

export function Toaster({ ...props }: ToasterProps) {
  const { theme } = useTheme();

  return (
    <Sonner
      theme={(theme as ToasterProps["theme"]) ?? "light"}
      className="toaster group"
      closeButton
      duration={6000}
      icons={{
        success: <CircleCheckIcon className="size-4" />,
        info: <InfoIcon className="size-4" />,
        warning: <TriangleAlertIcon className="size-4" />,
        error: <OctagonXIcon className="size-4" />,
        loading: <Loader2Icon className="size-4 animate-spin" />,
      }}
      style={
        {
          zIndex: 100,
          "--normal-bg": "oklch(0.985 0.01 88)",
          "--normal-text": "oklch(0.24 0.02 55)",
          "--normal-border": "oklch(0.86 0.025 80)",
          "--success-bg": "var(--primary)",
          "--success-text": "var(--primary-foreground)",
          "--success-border": "color-mix(in oklab, var(--primary) 85%, black)",
          "--error-bg": "oklch(0.38 0.12 28)",
          "--error-text": "oklch(0.98 0.01 88)",
          "--error-border": "oklch(0.32 0.1 28)",
          "--border-radius": "var(--radius)",
        } as React.CSSProperties
      }
      toastOptions={{
        classNames: {
          toast: "cn-toast group-[.toaster]:shadow-lg",
          success: "cn-toast-success",
          error: "cn-toast-error",
          closeButton: "cn-toast-close",
        },
      }}
      {...props}
    />
  );
}
