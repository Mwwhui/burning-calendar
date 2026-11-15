"use client";

import { changeCss, fireCss } from "@/lib/colors";
import type { ChildChange } from "@/lib/data/types";
import { formatCompact, monthSpan } from "@/lib/format";
import type { FireStyle, MapLayer } from "@/features/explorer/store";

function Gradient({ stops }: { stops: string[] }) {
  return (
    <div className="h-1.5 w-full rounded-full" style={{ background: `linear-gradient(to right, ${stops.join(", ")})` }} />
  );
}

export function MapLegend({
  layer,
  fireStyle,
  maxDensity,
  change,
}: {
  layer: MapLayer;
  fireStyle: FireStyle;
  maxDensity?: number;
  change: ChildChange | null;
}) {
  if (layer === "playback" && !maxDensity) return null;
  if (layer === "recent") return null; // the recent bar explains its colours
  return (
    <div className="pointer-events-none absolute right-3 bottom-[158px] z-10 w-48 rounded-lg border bg-background/80 px-2.5 py-2 text-[10.5px] shadow-md backdrop-blur-md max-sm:hidden">
      {layer === "playback" && maxDensity ? (
        <>
          <div className="mb-1.5 font-medium">
            Fire days per 1,000 km²{fireStyle === "heat" ? " (smoothed)" : ""}
          </div>
          <Gradient stops={[0, 0.25, 0.5, 0.75, 1].map(fireCss)} />
          <div className="mt-1 flex justify-between text-muted-foreground tabular-nums">
            <span>1</span>
            <span>{formatCompact(Math.sqrt(maxDensity))}</span>
            <span>{formatCompact(maxDensity)}+</span>
          </div>
        </>
      ) : change ? (
        <>
          <div className="mb-1.5 font-medium">
            {monthSpan(change.throughMonth)} {change.year} vs typical
          </div>
          <Gradient stops={[-100, -50, 0, 50, 100].map((p) => changeCss(p))} />
          <div className="mt-1 flex justify-between text-muted-foreground">
            <span>less</span>
            <span>same</span>
            <span>more</span>
          </div>
          <div className="mt-1 text-muted-foreground">
            Typical = {change.baseYears[0]}–{change.baseYears[change.baseYears.length - 1]}, NOAA-20 only
          </div>
        </>
      ) : (
        <div className="text-muted-foreground">No sub-areas to compare here.</div>
      )}
    </div>
  );
}
