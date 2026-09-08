import * as React from "react"
import { cn } from "cn"
import { DictationMic } from "@/components/dictation"

function Textarea({ className, ...props }: React.ComponentProps<"textarea">) {
  const wrapRef = React.useRef<HTMLDivElement>(null)
  return (
    <div ref={wrapRef} className="relative flex min-h-0 min-w-0 flex-1 flex-col">
      <textarea
        data-slot="textarea"
        className={cn(
          "flex min-h-16 w-full rounded-lg border border-input bg-transparent px-2.5 py-2 pr-8 text-base transition-colors outline-none placeholder:text-muted-foreground focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50 disabled:cursor-not-allowed disabled:bg-input/50 disabled:opacity-50 aria-invalid:border-destructive aria-invalid:ring-3 aria-invalid:ring-destructive/20 md:text-sm dark:bg-input/30 dark:disabled:bg-input/80 dark:aria-invalid:border-destructive/50 dark:aria-invalid:ring-destructive/40",
          className
        )}
        {...props}
      />
      <DictationMic
        className="top-2 translate-y-0"
        target={() => wrapRef.current?.querySelector("textarea") ?? null}
      />
    </div>
  )
}

export { Textarea }
