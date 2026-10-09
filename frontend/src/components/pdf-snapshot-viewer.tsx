"use client";

import { useEffect, useRef, useState } from "react";

const PDF_WORKER_SRC = "/pdf.worker.min.mjs";

type PdfPaintStats = {
  status: number;
  pageCount: number;
  firstCanvasHeight: number;
  clientHeight: number;
  scrollHeight: number;
};

const PDF_MAX_CANVAS = 4096;
const PDF_FIRST_PAGES = 2;


export function PdfSnapshotViewer({
  archiveId,
  onReady,
  onFailed,
}: {
  archiveId: string;
  onReady?: () => void;
  onFailed?: (message: string) => void;
}) {
  const fileUrl = `/api/v1/archives/${encodeURIComponent(String(archiveId || ""))}/file`;
  const hostRef = useRef<HTMLDivElement>(null);
  const scrollerRef = useRef<HTMLDivElement>(null);
  const blobUrlRef = useRef<string | null>(null);
  const pdfRef = useRef<{ destroy?: () => Promise<unknown> } | null>(null);
  const onReadyRef = useRef(onReady);
  const onFailedRef = useRef(onFailed);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [stats, setStats] = useState<PdfPaintStats | null>(null);
  onReadyRef.current = onReady;
  onFailedRef.current = onFailed;

  const fail = (message: string) => {
    setLoading(false);
    setError(message);
    try {
      onFailedRef.current?.(message);
    } catch {
      /* never let a callback take down the app */
    }
  };

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) return;
    const onKey = (event: KeyboardEvent) => {
      try {
        let node: HTMLElement | null = scroller;
        let host: HTMLElement | null = null;
        while (node) {
          const style = window.getComputedStyle(node);
          if ((style.overflowY === "auto" || style.overflowY === "scroll") && node.scrollHeight > node.clientHeight + 1) {
            host = node;
            break;
          }
          node = node.parentElement;
        }
        if (!host) return;
        const line = 48;
        const page = Math.max(host.clientHeight - 24, 80);
        if (event.key === "ArrowDown") host.scrollTop += line;
        else if (event.key === "ArrowUp") host.scrollTop -= line;
        else if (event.key === "PageDown") host.scrollTop += page;
        else if (event.key === "PageUp") host.scrollTop -= page;
        else if (event.key === "Home") host.scrollTop = 0;
        else if (event.key === "End") host.scrollTop = host.scrollHeight;
        else return;
        event.preventDefault();
      } catch {
        /* ignore */
      }
    };
    scroller.addEventListener("keydown", onKey);
    return () => scroller.removeEventListener("keydown", onKey);
  }, []);

  useEffect(() => {
    const scroller = scrollerRef.current;
    if (!scroller) {
      fail("PDF pane is missing.");
      return;
    }
    let cancelled = false;
    let widthObserver: ResizeObserver | null = null;
    let widthTimer: number | undefined;
    let raf = 0;
    try {
      scroller.replaceChildren();
    } catch {
      fail("Could not prepare the PDF pane.");
      return;
    }
    setError(null);
    setLoading(true);
    setStats(null);

    const waitForWidth = () =>
      new Promise<number>((resolve) => {
        let settled = false;
        const finish = (width: number) => {
          if (settled) return;
          settled = true;
          widthObserver?.disconnect();
          widthObserver = null;
          if (widthTimer !== undefined) {
            window.clearTimeout(widthTimer);
            widthTimer = undefined;
          }
          if (raf) window.cancelAnimationFrame(raf);
          raf = 0;
          resolve(Math.max(1, width));
        };
        const read = () =>
          Math.max(
            scroller.clientWidth || 0,
            scroller.parentElement?.clientWidth || 0,
            hostRef.current?.clientWidth || 0,
          );
        const tick = () => {
          if (cancelled) {
            finish(0);
            return;
          }
          const width = read();
          if (width > 0) {
            finish(width);
            return;
          }
          raf = window.requestAnimationFrame(tick);
        };
        try {
          widthObserver = new ResizeObserver(() => {
            const width = read();
            if (width > 0) finish(width);
          });
          widthObserver.observe(scroller);
        } catch {
          /* ResizeObserver missing */
        }
        tick();
        widthTimer = window.setTimeout(() => finish(Math.max(read(), 320)), 8000);
      });

    // pdf.js page objects are typed more strictly than we need here.
    const paintPage = async (doc: { getPage: (n: number) => Promise<any> }, pageNumber: number, width: number) => {
      const page = await doc.getPage(pageNumber);
      const unscaled = page.getViewport({ scale: 1 });
      const pageWidth = unscaled.width || 1;
      const pageHeight = unscaled.height || 1;
      let scale = width / pageWidth;
      if (!Number.isFinite(scale) || scale <= 0) scale = 1;
      const maxScale = Math.min(PDF_MAX_CANVAS / pageWidth, PDF_MAX_CANVAS / pageHeight);
      scale = Math.min(scale, maxScale);
      const viewport = page.getViewport({ scale });
      const wrap = document.createElement("div");
      wrap.className = "pdf-page";
      wrap.style.display = "block";
      wrap.style.width = "100%";
      const canvas = document.createElement("canvas");
      canvas.width = Math.max(1, Math.floor(viewport.width));
      canvas.height = Math.max(1, Math.floor(viewport.height));
      canvas.style.display = "block";
      canvas.style.width = "100%";
      canvas.style.height = "auto";
      canvas.style.pointerEvents = "none";
      wrap.appendChild(canvas);
      const context = canvas.getContext("2d", { alpha: false });
      if (!context) throw new Error("Could not draw the PDF snapshot.");
      await page.render({ canvasContext: context, viewport }).promise;
      if (!cancelled) scroller.appendChild(wrap);
      return canvas;
    };

    void (async () => {
      try {
        if (!archiveId) throw new Error("This PDF restore is missing an archive id.");
        const response = await fetch(fileUrl, { credentials: "include", cache: "no-store" });
        let bodyText = "";
        const buffer = response.ok ? await response.arrayBuffer() : null;
        if (!response.ok || !buffer) {
          bodyText = (await response.text().catch(() => "")).slice(0, 80);
          throw new Error(`GET ${fileUrl} returned HTTP ${response.status}. ${bodyText}`.trim());
        }
        const bytes = new Uint8Array(buffer);
        const headText = Array.from(bytes.slice(0, 80), (byte) => String.fromCharCode(byte)).join("");
        if (!headText.startsWith("%PDF")) {
          throw new Error(`Archive file is not a PDF (HTTP ${response.status}). First bytes: ${headText.slice(0, 80)}`);
        }
        if (cancelled) return;
        const pdfjs = await import("pdfjs-dist");
        pdfjs.GlobalWorkerOptions.workerSrc = PDF_WORKER_SRC;
        const loadingTask = pdfjs.getDocument({ data: bytes.slice() });
        const doc = await loadingTask.promise;
        pdfRef.current = doc;
        const pageCount = Number(doc.numPages) || 0;
        if (pageCount < 1) throw new Error("That PDF has no pages.");
        const width = await waitForWidth();
        if (cancelled) return;
        if (width <= 0) throw new Error("The PDF pane has no width yet.");
        const firstLimit = Math.min(PDF_FIRST_PAGES, pageCount);
        let firstCanvas: HTMLCanvasElement | null = null;
        for (let pageNumber = 1; pageNumber <= firstLimit; pageNumber += 1) {
          if (cancelled) return;
          const canvas = await paintPage(doc, pageNumber, width);
          if (pageNumber === 1) firstCanvas = canvas;
        }
        const firstHeight = firstCanvas
          ? Math.round(firstCanvas.getBoundingClientRect().height) || firstCanvas.height
          : 0;
        if (firstHeight <= 0) throw new Error("PDF pages rendered with no height.");
        if (cancelled) return;
        setStats({
          status: response.status,
          pageCount,
          firstCanvasHeight: firstHeight,
          clientHeight: scroller.clientHeight,
          scrollHeight: scroller.scrollHeight,
        });
        setLoading(false);
        try {
          onReadyRef.current?.();
        } catch {
          /* keep HTML if parent callback throws */
        }
        for (let pageNumber = firstLimit + 1; pageNumber <= pageCount; pageNumber += 1) {
          if (cancelled) return;
          await new Promise<void>((resolve) => window.requestAnimationFrame(() => resolve()));
          if (cancelled) return;
          await paintPage(doc, pageNumber, width);
        }
      } catch (caught) {
        if (cancelled) return;
        const message = caught instanceof Error ? caught.message : "Could not load the PDF snapshot.";
        fail(message);
      }
    })();

    return () => {
      cancelled = true;
      widthObserver?.disconnect();
      if (widthTimer !== undefined) window.clearTimeout(widthTimer);
      if (raf) window.cancelAnimationFrame(raf);
      try {
        scroller.replaceChildren();
      } catch {
        /* ignore */
      }
      const pdf = pdfRef.current;
      pdfRef.current = null;
      void Promise.resolve()
        .then(() => pdf?.destroy?.())
        .catch(() => undefined)
        .finally(() => {
          if (blobUrlRef.current) {
            URL.revokeObjectURL(blobUrlRef.current);
            blobUrlRef.current = null;
          }
        });
    };
  }, [archiveId, fileUrl]);

  return (
    <div
      ref={hostRef}
      className="pdf-host bg-muted"
      data-pdf-pending={loading && !error ? "1" : undefined}
      data-pdf-failed={error ? "1" : undefined}
    >
      {error ? <p className="reader-chrome px-3 py-2 text-sm text-destructive">{error}</p> : null}
      {loading && !error ? (
        <p className="reader-chrome px-3 py-2 text-sm text-muted-foreground">Loading PDF snapshot…</p>
      ) : null}
      {stats && !error ? (
        <p className="reader-chrome px-3 py-1 text-[0.7rem] text-muted-foreground">
          {stats.pageCount} page{stats.pageCount === 1 ? "" : "s"} · HTTP {stats.status} · first canvas{" "}
          {stats.firstCanvasHeight}px
        </p>
      ) : null}
      <div
        ref={scrollerRef}
        className="pdf-scroller"
        tabIndex={0}
        role="region"
        aria-label="PDF snapshot"
      />
    </div>
  );
}
