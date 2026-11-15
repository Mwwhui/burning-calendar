"use client";

import { useCallback, useEffect, useRef, useSyncExternalStore } from "react";

import { clampPanel, PANEL_DEFAULT, PANEL_MIN, panelMax } from "../lib/panel-width";

/**
 * Drag handle on the side panel's left edge (desktop only). Drag, or focus it and use the arrow keys;
 * double-click resets the width.
 */
function onResize(cb: () => void) {
  window.addEventListener("resize", cb);
  return () => window.removeEventListener("resize", cb);
}

export function PanelResizer({ width, onChange }: { width: number; onChange: (w: number) => void }) {
  const drag = useRef<{ x: number; w: number } | null>(null);
  // viewport width from the browser only (null in the server render, so hydration matches)
  const viewport = useSyncExternalStore(onResize, () => window.innerWidth, () => null);

  const move = useCallback(
    (e: PointerEvent) => {
      const d = drag.current;
      if (d) onChange(clampPanel(d.w + (d.x - e.clientX), window.innerWidth));
    },
    [onChange],
  );
  const up = useCallback(() => {
    drag.current = null;
    document.body.style.cursor = "";
    document.body.style.userSelect = "";
  }, []);

  useEffect(() => {
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, [move, up]);

  return (
    <div
      role="separator"
      aria-orientation="vertical"
      aria-label="Resize the side panel"
      aria-valuemin={PANEL_MIN}
      aria-valuemax={viewport === null ? undefined : panelMax(viewport)}
      aria-valuenow={width}
      tabIndex={0}
      title="Drag to resize · double-click to reset"
      onPointerDown={(e) => {
        e.preventDefault();
        drag.current = { x: e.clientX, w: width };
        document.body.style.cursor = "col-resize";
        document.body.style.userSelect = "none";
      }}
      onDoubleClick={() => onChange(clampPanel(PANEL_DEFAULT, window.innerWidth))}
      onKeyDown={(e) => {
        const step = e.shiftKey ? 80 : 20;
        if (e.key === "ArrowLeft") onChange(clampPanel(width + step, window.innerWidth));
        else if (e.key === "ArrowRight") onChange(clampPanel(width - step, window.innerWidth));
        else return;
        e.preventDefault();
      }}
      className="group absolute inset-y-0 -left-1.5 z-30 hidden w-3 cursor-col-resize touch-none outline-none md:block"
    >
      <span className="absolute inset-y-0 left-1/2 w-px -translate-x-1/2 bg-transparent transition-colors group-hover:w-0.5 group-hover:bg-primary/60 group-focus-visible:w-0.5 group-focus-visible:bg-primary" />
      <span className="absolute top-1/2 left-1/2 h-8 w-1 -translate-x-1/2 -translate-y-1/2 rounded-full bg-border group-hover:bg-primary/70" />
    </div>
  );
}
