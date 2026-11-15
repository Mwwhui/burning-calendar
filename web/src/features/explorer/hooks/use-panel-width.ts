"use client";

import { useCallback, useSyncExternalStore } from "react";

import { clampPanel, PANEL_KEY } from "../lib/panel-width";

// The chosen width lives in localStorage (this browser only) with an in-memory copy for when storage is
// blocked; components read it through useSyncExternalStore, so the server render (null = default width)
// and the browser agree on first paint.
const listeners = new Set<() => void>();
let memory: number | null = null;

function read(): number | null {
  try {
    const v = Number(localStorage.getItem(PANEL_KEY));
    if (v) return clampPanel(v, window.innerWidth);
  } catch {
    /* storage blocked */
  }
  return memory;
}

function subscribe(cb: () => void) {
  listeners.add(cb);
  window.addEventListener("resize", cb);
  return () => {
    listeners.delete(cb);
    window.removeEventListener("resize", cb);
  };
}

export function usePanelWidth(): [number | null, (w: number) => void] {
  const width = useSyncExternalStore(subscribe, read, () => null);
  const set = useCallback((w: number) => {
    memory = w;
    try {
      localStorage.setItem(PANEL_KEY, String(w));
    } catch {
      /* storage blocked: the in-memory width still applies until reload */
    }
    listeners.forEach((l) => l());
  }, []);
  return [width, set];
}
