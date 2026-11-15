"use client";

import { useEffect } from "react";

import { FRAME_MS, useExplorer } from "@/features/explorer/store";

/**
 * Advances the playback frame while playing; stops on the last period.
 * Space toggles play/pause, arrow keys step one period.
 */
export function usePlaybackTicker(nPeriods: number) {
  const { playing, step, speed, frame, setFrame, setPlaying } = useExplorer();
  const last = nPeriods - 1;
  const current = frame ?? last;

  useEffect(() => {
    if (!playing || nPeriods === 0) return;
    if (current >= last) {
      setPlaying(false);
      return;
    }
    const t = window.setTimeout(() => setFrame(current + 1), FRAME_MS[step][speed]);
    return () => window.clearTimeout(t);
  }, [playing, current, last, nPeriods, step, speed, setFrame, setPlaying]);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      const el = e.target as HTMLElement | null;
      if (el && (el.isContentEditable || ["INPUT", "TEXTAREA", "SELECT"].includes(el.tagName))) return;
      if (nPeriods === 0) return;
      if (e.key === " ") {
        e.preventDefault();
        togglePlay();
      } else if (e.key === "ArrowLeft") {
        setPlaying(false);
        setFrame(Math.max(0, current - 1));
      } else if (e.key === "ArrowRight") {
        setPlaying(false);
        setFrame(Math.min(last, current + 1));
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  });

  function togglePlay() {
    if (playing) {
      setPlaying(false);
    } else {
      if (current >= last) setFrame(0); // replay from the start
      setPlaying(true);
    }
  }

  return { current, last, togglePlay };
}
