"use client";

import {
  forwardRef,
  useCallback,
  useEffect,
  useImperativeHandle,
  useRef,
  useState,
  type KeyboardEvent as ReactKeyboardEvent,
  type PointerEvent as ReactPointerEvent,
} from "react";
import { createPortal } from "react-dom";
import { Calculator, Maximize2, Minimize2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { evaluateExpression, looksLikeSchoolPaper, pushCalcHistory, type AngleMode } from "@/lib/calculator";
import {
  applyCalcResize,
  clampCalcBox,
  type CalcResizeEdge,
} from "@/lib/calculator-layout";
import { loadCalcStored, saveCalcStored } from "@/lib/calculator-storage";
import { cn } from "@/lib/utils";

export type CalculatorHandle = { open: () => void };

const RESIZE_HANDLES: { edge: CalcResizeEdge; className: string; label: string }[] = [
  { edge: "n", className: "left-3 right-3 top-0 h-1.5 cursor-ns-resize", label: "Resize top" },
  { edge: "s", className: "left-3 right-3 bottom-0 h-1.5 cursor-ns-resize", label: "Resize bottom" },
  { edge: "e", className: "top-3 bottom-3 right-0 w-1.5 cursor-ew-resize", label: "Resize right" },
  { edge: "w", className: "top-3 bottom-3 left-0 w-1.5 cursor-ew-resize", label: "Resize left" },
  { edge: "ne", className: "right-0 top-0 size-3 cursor-nesw-resize", label: "Resize top right" },
  { edge: "nw", className: "left-0 top-0 size-3 cursor-nwse-resize", label: "Resize top left" },
  { edge: "se", className: "right-0 bottom-0 size-4 cursor-se-resize", label: "Resize bottom right" },
  { edge: "sw", className: "left-0 bottom-0 size-3 cursor-nesw-resize", label: "Resize bottom left" },
];

type KeySpec = { label: string; insert?: string; action?: string; wide?: boolean; tone?: "op" | "fn" | "eq" | "mem" };

const KEYS: KeySpec[][] = [
  [
    { label: "MC", action: "mc", tone: "mem" },
    { label: "MR", action: "mr", tone: "mem" },
    { label: "M+", action: "mplus", tone: "mem" },
    { label: "M−", action: "mminus", tone: "mem" },
    { label: "C", action: "clear" },
  ],
  [
    { label: "sin", insert: "sin(", tone: "fn" },
    { label: "cos", insert: "cos(", tone: "fn" },
    { label: "tan", insert: "tan(", tone: "fn" },
    { label: "log", insert: "log(", tone: "fn" },
    { label: "ln", insert: "ln(", tone: "fn" },
  ],
  [
    { label: "(", insert: "(" },
    { label: ")", insert: ")" },
    { label: "√", insert: "sqrt(", tone: "fn" },
    { label: "x^y", insert: "^", tone: "fn" },
    { label: "n!", insert: "!", tone: "fn" },
  ],
  [
    { label: "π", insert: "pi", tone: "fn" },
    { label: "e", insert: "e", tone: "fn" },
    { label: "exp", insert: "exp(", tone: "fn" },
    { label: "1/x", action: "inv", tone: "fn" },
    { label: "±", action: "neg" },
  ],
  [
    { label: "7", insert: "7" },
    { label: "8", insert: "8" },
    { label: "9", insert: "9" },
    { label: "÷", insert: "÷", tone: "op" },
    { label: "%", insert: "%", tone: "op" },
  ],
  [
    { label: "4", insert: "4" },
    { label: "5", insert: "5" },
    { label: "6", insert: "6" },
    { label: "×", insert: "×", tone: "op" },
    { label: "⌫", action: "back" },
  ],
  [
    { label: "1", insert: "1" },
    { label: "2", insert: "2" },
    { label: "3", insert: "3" },
    { label: "−", insert: "−", tone: "op" },
    { label: "°", insert: "°", tone: "fn" },
  ],
  [
    { label: "0", insert: "0", wide: true },
    { label: ".", insert: "." },
    { label: "+", insert: "+", tone: "op" },
    { label: "=", action: "eq", tone: "eq" },
  ],
];

export const CalculatorOverlay = forwardRef<CalculatorHandle, { userId: string }>(function CalculatorOverlay(
  { userId },
  ref,
) {
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [fullscreen, setFullscreen] = useState(false);
  const [expr, setExpr] = useState("");
  const [output, setOutput] = useState("");
  const [error, setError] = useState<string | null>(null);
  const stored = () => loadCalcStored(userId, window.innerWidth, window.innerHeight);
  const [angle, setAngle] = useState<AngleMode>("deg");
  const [memory, setMemory] = useState(0);
  const [history, setHistory] = useState<{ expr: string; result: string }[]>([]);
  const [panel, setPanel] = useState({ x: 24, y: 24, w: 360, h: 580 });
  const dragRef = useRef<{ dx: number; dy: number } | null>(null);
  const resizeRef = useRef<{ edge: CalcResizeEdge; startX: number; startY: number; box: { left: number; top: number; w: number; h: number } } | null>(null);
  const panelRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    setMounted(true);
    const next = stored();
    setPanel(next.panel);
    setHistory(next.history);
    setAngle(next.angle);
    setMemory(next.memory);
  }, [userId]);

  useEffect(() => {
    if (!mounted) return;
    saveCalcStored(userId, { panel, history, angle, memory });
  }, [angle, history, memory, mounted, panel, userId]);

  const openPanel = useCallback(() => {
    setOpen(true);
    setFullscreen(false);
    window.setTimeout(() => {
      panelRef.current?.focus();
      inputRef.current?.focus();
    }, 0);
  }, []);

  useImperativeHandle(ref, () => ({ open: openPanel }), [openPanel]);

  const closePanel = useCallback(() => {
    setFullscreen(false);
    setOpen(false);
  }, []);

  const panelBox = clampCalcBox(
    { left: panel.x, top: panel.y, w: panel.w, h: panel.h },
    typeof window === "undefined" ? 1200 : window.innerWidth,
    typeof window === "undefined" ? 800 : window.innerHeight,
  );

  useEffect(() => {
    function onResize() {
      const vw = window.innerWidth;
      const vh = window.innerHeight;
      if (!open || fullscreen) return;
      const next = clampCalcBox({ left: panel.x, top: panel.y, w: panel.w, h: panel.h }, vw, vh);
      setPanel({ x: next.left, y: next.top, w: next.w, h: next.h });
    }
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [fullscreen, open, panel.h, panel.w, panel.x, panel.y]);

  const evaluate = useCallback(
    (source = expr) => {
      const result = evaluateExpression(source, angle);
      if (!result.ok) {
        setError(result.error);
        setOutput("");
        return;
      }
      setError(null);
      setOutput(result.display);
      setHistory((current) => pushCalcHistory(current, { expr: source.trim(), result: result.display }));
    },
    [angle, expr],
  );

  const insert = useCallback((chunk: string) => {
    setError(null);
    setExpr((current) => `${current}${chunk}`);
  }, []);

  const runAction = useCallback(
    (action: string) => {
      if (action === "clear") {
        setExpr("");
        setOutput("");
        setError(null);
        return;
      }
      if (action === "back") {
        setExpr((current) => current.slice(0, -1));
        return;
      }
      if (action === "eq") {
        evaluate();
        return;
      }
      if (action === "mc") {
        setMemory(0);
        return;
      }
      if (action === "mr") {
        insert(String(memory));
        return;
      }
      if (action === "mplus" || action === "mminus") {
        const result = evaluateExpression(expr || output, angle);
        if (!result.ok) {
          setError(result.error);
          return;
        }
        setMemory((current) => current + (action === "mplus" ? result.value : -result.value));
        return;
      }
      if (action === "inv") {
        setExpr((current) => (current.trim() ? `inv(${current})` : "inv("));
        return;
      }
      if (action === "neg") {
        setExpr((current) => {
          const trimmed = current.trim();
          if (!trimmed) return "-";
          if (trimmed.startsWith("-(") && trimmed.endsWith(")")) return trimmed.slice(2, -1);
          return `-(${trimmed})`;
        });
      }
    },
    [angle, evaluate, expr, insert, memory, output],
  );

  useEffect(() => {
    function onMove(event: PointerEvent) {
      const drag = dragRef.current;
      if (drag) {
        if (!fullscreen) {
          const next = clampCalcBox(
            { left: event.clientX - drag.dx, top: event.clientY - drag.dy, w: panelBox.w, h: panelBox.h },
            window.innerWidth,
            window.innerHeight,
          );
          setPanel({ x: next.left, y: next.top, w: next.w, h: next.h });
        }
        return;
      }
      const resize = resizeRef.current;
      if (!resize || fullscreen) return;
      const next = applyCalcResize(
        resize.box,
        resize.edge,
        event.clientX - resize.startX,
        event.clientY - resize.startY,
        window.innerWidth,
        window.innerHeight,
      );
      setPanel({ x: next.left, y: next.top, w: next.w, h: next.h });
    }
    function onUp() {
      dragRef.current = null;
      resizeRef.current = null;
      document.body.style.userSelect = "";
    }
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onUp);
    };
  }, [fullscreen, panelBox.h, panelBox.w]);

  useEffect(() => {
    function onKey(event: KeyboardEvent) {
      if (!open) return;
      if (event.key !== "Escape") return;
      event.preventDefault();
      event.stopPropagation();
      if (fullscreen) {
        setFullscreen(false);
        return;
      }
      closePanel();
    }
    window.addEventListener("keydown", onKey, true);
    return () => window.removeEventListener("keydown", onKey, true);
  }, [fullscreen, open, closePanel]);

  function onPanelKey(event: ReactKeyboardEvent<HTMLDivElement>) {
    const target = event.target as HTMLElement | null;
    if (target?.closest("textarea")) return;
    if (event.key === "Enter") {
      event.preventDefault();
      evaluate();
      return;
    }
    if (event.key === "Backspace" && target !== inputRef.current) {
      event.preventDefault();
      runAction("back");
      return;
    }
    const map: Record<string, string> = {
      "*": "×",
      "/": "÷",
      "-": "−",
    };
    if (/^[0-9.+\-*/^%()]$/.test(event.key)) {
      if (target === inputRef.current) return;
      event.preventDefault();
      insert(map[event.key] || event.key);
    }
  }

  function onExprPaste(event: React.ClipboardEvent<HTMLInputElement>) {
    const text = event.clipboardData.getData("text");
    if (looksLikeSchoolPaper(text)) {
      event.preventDefault();
      setError("Paste one expression, not a paper.");
    }
  }

  if (!mounted || !open) return null;

  const panelEl = (
    <div
      ref={panelRef}
      tabIndex={0}
      onKeyDown={onPanelKey}
      className={cn(
        "fixed flex min-h-0 flex-col overflow-hidden border bg-popover text-popover-foreground shadow-xl outline-none",
        fullscreen ? "inset-0 z-[90] h-[100dvh] w-[100vw] rounded-none" : "z-[75] rounded-xl",
      )}
      style={
        fullscreen
          ? undefined
          : { left: panelBox.left, top: panelBox.top, width: panelBox.w, height: panelBox.h }
      }
      aria-label="Calculator"
    >
      <div
        data-drag-handle
        className={cn(
          "flex shrink-0 items-center gap-2 border-b px-3 py-2",
          fullscreen ? "cursor-default" : "cursor-grab active:cursor-grabbing",
        )}
        onPointerDown={(event: ReactPointerEvent<HTMLDivElement>) => {
          if (fullscreen) return;
          if ((event.target as HTMLElement).closest("button, [data-resize]")) return;
          dragRef.current = {
            dx: event.clientX - panelBox.left,
            dy: event.clientY - panelBox.top,
          };
        }}
      >
        <Calculator className="size-4 text-primary" />
        <div className="min-w-0 flex-1">
          <p className="truncate text-sm font-medium leading-none">Calculator</p>
          <p className="truncate text-[11px] text-muted-foreground">{angle === "deg" ? "Degrees" : "Radians"}</p>
        </div>
        <Button
          type="button"
          size="xs"
          variant={angle === "deg" ? "default" : "outline"}
          className="h-7 px-2 text-xs"
          onClick={() => setAngle((current) => (current === "deg" ? "rad" : "deg"))}
        >
          {angle === "deg" ? "Deg" : "Rad"}
        </Button>
        {fullscreen ? (
          <Button size="sm" variant="ghost" className="h-7 px-2 text-xs" onClick={() => setFullscreen(false)}>
            <Minimize2 className="size-3.5" />
            Exit full screen
          </Button>
        ) : (
          <Button size="icon-xs" variant="ghost" onClick={() => setFullscreen(true)} aria-label="Full screen" title="Full screen">
            <Maximize2 className="size-3.5" />
          </Button>
        )}
        <Button size="icon-xs" variant="ghost" onClick={closePanel} aria-label="Close calculator">
          <X className="size-3.5" />
        </Button>
      </div>
      <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-hidden p-3">
        {history.length ? (
          <ul className="max-h-24 shrink-0 overflow-y-auto rounded-md border bg-muted/30 px-2 py-1 text-[11px] text-muted-foreground">
            {history.map((item, index) => (
              <li key={`${item.expr}-${index}`}>
                <button
                  type="button"
                  className="block w-full truncate text-left hover:text-foreground"
                  onClick={() => {
                    setExpr(item.expr);
                    setOutput(item.result);
                    setError(null);
                  }}
                >
                  {item.expr} = {item.result}
                </button>
              </li>
            ))}
          </ul>
        ) : (
          <p className="shrink-0 text-[11px] text-muted-foreground">One expression line. History stays on this device.</p>
        )}
        <input
          ref={inputRef}
          value={expr}
          onChange={(event) => {
            setExpr(event.target.value.replace(/[\r\n]/g, ""));
            setError(null);
          }}
          onPaste={onExprPaste}
          onKeyDown={(event) => {
            if (event.key === "Enter") {
              event.preventDefault();
              evaluate();
            }
          }}
          aria-label="Expression"
          inputMode="decimal"
          autoComplete="off"
          spellCheck={false}
          className="h-9 shrink-0 rounded-md border bg-background px-2 font-mono text-sm outline-none focus-visible:border-ring focus-visible:ring-3 focus-visible:ring-ring/50"
          placeholder="2^10 or sin(30°)"
        />
        <p className={cn("min-h-6 shrink-0 font-mono text-lg tabular-nums", error ? "text-destructive" : "text-foreground")}>
          {error || output || "\u00a0"}
        </p>
        <div className="grid min-h-0 flex-1 grid-cols-5 gap-1 overflow-auto content-start">
          {KEYS.flatMap((row, rowIndex) =>
            row.map((key) => (
              <Button
                key={`${rowIndex}-${key.label}`}
                type="button"
                size="xs"
                variant={key.tone === "eq" ? "default" : key.tone === "op" || key.tone === "fn" || key.tone === "mem" ? "secondary" : "outline"}
                className={cn("h-8 min-h-8 font-mono text-xs", key.wide && "col-span-2")}
                onClick={() => {
                  if (key.action) runAction(key.action);
                  else if (key.insert) insert(key.insert);
                }}
              >
                {key.label}
              </Button>
            )),
          )}
        </div>
      </div>
      {!fullscreen
        ? RESIZE_HANDLES.map((handle) => (
            <div
              key={handle.edge}
              data-resize={handle.edge}
              role="separator"
              aria-label={handle.label}
              className={cn("absolute z-20 touch-none", handle.className)}
              onPointerDown={(event) => {
                event.preventDefault();
                event.stopPropagation();
                event.currentTarget.setPointerCapture(event.pointerId);
                document.body.style.userSelect = "none";
                resizeRef.current = {
                  edge: handle.edge,
                  startX: event.clientX,
                  startY: event.clientY,
                  box: panelBox,
                };
              }}
            />
          ))
        : null}
    </div>
  );

  return createPortal(panelEl, document.body);
});
