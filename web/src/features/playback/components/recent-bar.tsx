"use client";

import { useMemo } from "react";

import { useCurrentArea } from "@/features/explorer/hooks/use-area";
import { useExplorer } from "@/features/explorer/store";
import { countryOf } from "@/lib/area";
import { fireCss } from "@/lib/colors";
import { useRecent } from "@/lib/data/queries";
import { formatDay, formatInt } from "@/lib/format";

const STEPS = [1, 3, 7, 14, 30, 60];

/** Controls of the "Latest fires" layer: real detections of the last N days. */
export function RecentBar() {
  const { lookup, id } = useCurrentArea();
  const cid = lookup ? countryOf(lookup, id) : undefined;
  const { data, isLoading } = useRecent(cid);
  const days = useExplorer((s) => s.recentDays);
  const setDays = useExplorer((s) => s.setRecentDays);
  const perDay = useMemo(() => {
    const c = new Array(61).fill(0);
    data?.age.forEach((a) => a <= 60 && c[a]++);
    return c;
  }, [data]);
  const shown = perDay.slice(0, days + 1).reduce((a, b) => a + b, 0);
  const max = Math.max(1, ...perDay);

  return (
    <div className="absolute inset-x-3 bottom-3 z-10 rounded-xl border bg-background/88 p-3 shadow-lg backdrop-blur-md">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <span className="text-base font-semibold">Latest fires</span>{" "}
          <span className="text-sm text-muted-foreground tabular-nums">
            {isLoading ? "loading…" : `${formatInt(shown)} detections in the last ${days} day${days > 1 ? "s" : ""} to ${formatDay(data?.lastDay)}`}
          </span>
        </div>
        <div className="flex gap-1">
          {STEPS.map((d) => (
            <button
              key={d}
              type="button"
              onClick={() => setDays(d)}
              className={`rounded-md border px-2 py-0.5 text-xs ${d === days ? "border-foreground bg-foreground text-background" : "hover:bg-muted"}`}
            >
              {d}d
            </button>
          ))}
        </div>
      </div>
      {/* detections per day, newest on the right */}
      <div className="mt-2 flex h-10 items-end gap-px">
        {perDay
          .slice()
          .reverse()
          .map((n, k) => {
            const age = 60 - k;
            return (
              <div
                key={age}
                title={`${age === 0 ? "last day" : `${age} days before`}: ${n} detections`}
                className="flex-1 rounded-t-[1px]"
                style={{
                  height: `${Math.max(2, (n / max) * 100)}%`,
                  background: age <= days ? fireCss(0.15 + 0.85 * (age / Math.max(1, days))) : "var(--muted)",
                }}
              />
            );
          })}
      </div>
      <p className="mt-1.5 text-[11px] text-muted-foreground">
        Each dot is a real satellite detection (NOAA-20 VIIRS, cleaned, gas flares removed), not converted; size = fire
        strength (FRP), newest brightest. Cloud and smoke hide some fires.
      </p>
    </div>
  );
}
