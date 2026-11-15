"use client";

import { useSyncExternalStore } from "react";

const noop = () => () => {};

/** false during server rendering and hydration, true afterwards (for browser-only state). */
export function useIsClient(): boolean {
  return useSyncExternalStore(noop, () => true, () => false);
}
