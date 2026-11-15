"use client";

import { ChevronLeft, ChevronRight, X } from "lucide-react";

import { useExplorer } from "@/features/explorer/store";
import { HAZE_FIRST, HAZE_LEGEND, hazeColor, hazeLayer, shiftDay, type HazeKind } from "@/lib/gibs";
import { formatDay } from "@/lib/format";
import { cn } from "@/lib/utils";

import { latestPhotoDay } from "./photo-bar";

const GLASS = "rounded-lg border bg-background/88 shadow-md backdrop-blur-md";

const ABOUT: Record<HazeKind, string> = {
  aod: "How much haze dims the sunlight (aerosol optical depth), measured from the same satellite as the fire dots. Blank under cloud, and where smoke is so thick it is taken for cloud. ~6 km.",
  smoke: "Smoke and dust that absorb ultraviolet light (UV aerosol index), seen even above cloud: use it when the haze view is blank. Coarse (~17-50 km), from 2012.",
};

/** Controls of the haze / smoke veil: day, which measure, legend. */
export function HazeBar() {
  const haze = useExplorer((s) => s.haze);
  const setHaze = useExplorer((s) => s.setHaze);
  const photo = useExplorer((s) => s.photo);
  if (!haze) return null;
  const max = latestPhotoDay();
  // typing in the date box passes through half-typed years (e.g. 0006-11-13): ignore days before the record
  const go = (date: string) => date >= HAZE_FIRST[haze.kind] && setHaze({ ...haze, date: date > max ? max : date });
  const layer = hazeLayer(haze.date, haze.kind);
  const btn = "inline-flex h-6 items-center rounded-md border px-1.5 hover:bg-muted disabled:opacity-40";
  const seg = (on: boolean) => cn("px-2 py-0.5", on ? "bg-foreground text-background" : "hover:bg-muted");
  const swatch = (v: number) => {
    const [r, g, b, a] = hazeColor(v, haze.kind);
    return `rgba(${r},${g},${b},${(a / 255).toFixed(2)})`;
  };

  return (
    <div className={cn(GLASS, "pointer-events-auto absolute top-12 right-12 z-10 w-[min(17rem,calc(100%-4.5rem))] p-2 text-xs max-sm:top-auto max-sm:right-3 max-sm:bottom-40")}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">
          Haze &amp; smoke {layer && <span className="text-muted-foreground">· {layer.name}</span>}
        </span>
        <button type="button" aria-label="Hide haze" className="inline-flex h-6 items-center rounded-md px-1 hover:bg-muted" onClick={() => setHaze(null)}>
          <X className="size-3.5" />
        </button>
      </div>
      <div className="mt-1.5 flex flex-wrap items-center gap-1">
        <button type="button" aria-label="Day before" className={btn} onClick={() => go(shiftDay(haze.date, -1))}>
          <ChevronLeft className="size-3.5" />
        </button>
        <input
          type="date"
          aria-label="Day of the haze map"
          value={haze.date}
          min={HAZE_FIRST[haze.kind]}
          max={max}
          onChange={(e) => e.target.value && go(e.target.value)}
          className="h-6 rounded-md border bg-background px-1.5 tabular-nums"
        />
        <button type="button" aria-label="Day after" disabled={haze.date >= max} className={btn} onClick={() => go(shiftDay(haze.date, 1))}>
          <ChevronRight className="size-3.5" />
        </button>
        {photo && photo.date !== haze.date && (
          <button type="button" className="rounded-md border px-1.5 py-0.5 hover:bg-muted" onClick={() => go(photo.date)}>
            photo day
          </button>
        )}
      </div>
      <div className="mt-1.5 inline-flex overflow-hidden rounded-md border" role="group" aria-label="Haze measure">
        <button type="button" className={seg(haze.kind === "aod")} onClick={() => setHaze({ ...haze, kind: "aod" })}>
          Haze
        </button>
        <button type="button" className={cn(seg(haze.kind === "smoke"), "border-l")} onClick={() => setHaze({ ...haze, kind: "smoke" })}>
          Smoke above cloud
        </button>
      </div>
      {layer ? (
        <div className="mt-1.5 grid gap-0.5">
          {HAZE_LEGEND[haze.kind].map((l) => (
            <span key={l.label} className="flex items-center gap-1.5">
              <span className="inline-block h-2.5 w-5 shrink-0 rounded-sm border" style={{ background: swatch(l.v) }} />
              {l.label}
            </span>
          ))}
        </div>
      ) : (
        <p className="mt-1.5 text-muted-foreground">Not available before {formatDay(HAZE_FIRST[haze.kind])}.</p>
      )}
      <p className="mt-1.5 leading-snug text-muted-foreground">{ABOUT[haze.kind]}</p>
    </div>
  );
}
