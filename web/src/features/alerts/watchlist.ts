"use client";

import { create } from "zustand";
import { createJSONStorage, persist } from "zustand/middleware";

import type { AlertItem } from "@/lib/data/types";

interface WatchState {
  /** watched area ids ("" = all of Asia) */
  ids: string[];
  /** `generated` stamp of the last alerts a browser notification was shown for */
  notified: string | null;
  toggle: (id: string) => void;
  setNotified: (g: string) => void;
}

/** Areas the user watches, kept in this browser only (localStorage; nothing is sent anywhere). */
export const useWatchlist = create<WatchState>()(
  persist(
    (set) => ({
      ids: [],
      notified: null,
      toggle: (id) => set((s) => ({ ids: s.ids.includes(id) ? s.ids.filter((x) => x !== id) : [...s.ids, id] })),
      setNotified: (notified) => set({ notified }),
    }),
    {
      name: "burning-calendar:watchlist",
      storage: createJSONStorage(() => {
        try {
          return window.localStorage;
        } catch {
          return {
            getItem: () => null,
            setItem: () => undefined,
            removeItem: () => undefined,
          };
        }
      }),
    },
  ),
);

/** An alert concerns a watched area when it is that area or inside it (watching Malaysia covers Sarawak). */
export function isWatched(alert: AlertItem, ids: string[]): boolean {
  return ids.some((w) => w === "" || alert.areaId === w || alert.areaId.startsWith(`${w}/`));
}
