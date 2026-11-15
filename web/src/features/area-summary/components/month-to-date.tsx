"use client";

import { useMemo } from "react";

import { compareWindow, DailyIndex, pctOk, windowTotals } from "@/lib/analytics/window";
import { useDaily } from "@/lib/data/queries";
import type { MonthlySeries } from "@/lib/data/types";
import { formatInt, MONTHS_SHORT } from "@/lib/format";
import { cn } from "@/lib/utils";

/**
 * "This month so far vs the median of the same days" (the Streamlit headline):
 * 1st of the latest month to the last complete day, compared with the same dates of every
 * other year (burncal.daily.window_totals / compare_window).
 */
export function MonthToDate({ listedId, series, lastDay }: { listedId: string; series: MonthlySeries; lastDay: string }) {
  const { data: daily } = useDaily(listedId);
  const c = useMemo(() => {
    if (!daily) return null;
    try {
      const start = `${lastDay.slice(0, 8)}01`;
      const rows = windowTotals(series, new DailyIndex(daily), start, lastDay, lastDay);
      return compareWindow(rows, Number(lastDay.slice(0, 4)));
    } catch {
      return null;
    }
  }, [daily, series, lastDay]);
  if (!c) return null;
  const d = Number(lastDay.slice(8, 10));
  const m = MONTHS_SHORT[Number(lastDay.slice(5, 7)) - 1];
  const days = d === 1 ? `1 ${m}` : `1–${d} ${m} ${lastDay.slice(0, 4)}`;
  const ok = pctOk(c);
  const up = ok && c.pctVsMedian! > 0;
  return (
    <div className="rounded-xl border bg-card/60 p-3">
      <div className="text-[11px] text-muted-foreground">This month so far · {days}</div>
      <div className="mt-0.5 flex flex-wrap items-baseline gap-x-2">
        <span className="text-lg font-semibold tabular-nums">{formatInt(c.total)} fire days</span>
        {ok ? (
          <span className={cn("text-sm font-medium", up ? "text-red-500" : "text-sky-500")}>
            {Math.abs(Math.round(c.pctVsMedian!))} % {up ? "more" : "less"} than usual
          </span>
        ) : (
          <span className="text-sm text-muted-foreground">usually about {formatInt(c.median)}</span>
        )}
      </div>
      <div className="text-[11px] text-muted-foreground">
        Median of the same days in {c.firstYear}–{c.year - 1}: {formatInt(c.median)}. Rank #{c.rank} of {c.nYears} (#1 = most fire).
        {c.estimated && c.lower <= c.median && c.median <= c.upper && " Its likely range includes the median, so it is not clearly unusual."}
      </div>
    </div>
  );
}
