import { ArrowDownRight, ArrowUpRight, Minus } from "lucide-react";

import type { Summary } from "@/lib/data/types";
import { formatInt, formatPct, MONTHS_LONG, monthSpan, ordinal } from "@/lib/format";
import { cn } from "@/lib/utils";

export function Headline({ s }: { s: Summary }) {
  const p = s.pctVsMedian;
  if (p === null) return null;
  const up = p >= 5;
  const down = p <= -5;
  const Icon = up ? ArrowUpRight : down ? ArrowDownRight : Minus;
  return (
    <p className="flex items-center gap-2 text-sm">
      <span
        className={cn(
          "inline-flex items-center gap-0.5 rounded-full px-2 py-0.5 text-xs font-semibold",
          up && "bg-red-500/15 text-red-600 dark:text-red-400",
          down && "bg-sky-500/15 text-sky-700 dark:text-sky-300",
          !up && !down && "bg-muted text-muted-foreground",
        )}
      >
        <Icon className="size-3.5" />
        {formatPct(p)}
      </span>
      <span className="text-muted-foreground">
        {monthSpan(s.throughMonth)} {s.thisYear} vs the median year
      </span>
    </p>
  );
}

function Metric({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="rounded-lg border bg-card p-3">
      <div className="text-[11px] text-muted-foreground">{label}</div>
      <div className="mt-0.5 text-xl font-semibold tabular-nums">{value}</div>
      {sub && <div className="text-[11px] text-muted-foreground">{sub}</div>}
    </div>
  );
}

export function Metrics({ s, unit }: { s: Summary; unit: string }) {
  return (
    <div className="grid grid-cols-2 gap-2">
      <Metric
        label={`Fire days, ${monthSpan(s.throughMonth)} ${s.thisYear}`}
        value={formatInt(s.thisYearToDate)}
        sub={`${ordinal(s.rank)} highest of ${s.nYears} years`}
      />
      <Metric label="vs median year, same months" value={formatPct(s.pctVsMedian)} sub={unit} />
      <Metric
        label="Busiest year"
        value={s.busiestYear ? String(s.busiestYear) : "–"}
        sub={`${formatInt(s.busiestYearTotal)} ${unit}${s.busiestYearEstimated ? " (est.)" : ""}`}
      />
      <Metric
        label="Peak month"
        value={MONTHS_LONG[s.peakMonth - 1]}
        sub={s.peakShare !== null ? `${Math.round(s.peakShare * 100)} % of a typical year` : undefined}
      />
    </div>
  );
}
