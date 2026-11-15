"use client";

import { Download, ExternalLink } from "lucide-react";
import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ErrorBar, ReferenceLine, XAxis, YAxis } from "recharts";

import { Callout, Empty, Note, Section } from "@/components/common/section";
import { Button } from "@/components/ui/button";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { Input } from "@/components/ui/input";
import { useCurrentArea } from "@/features/explorer/hooks/use-area";
import { useExplorer } from "@/features/explorer/store";
import { compareWindow, DailyIndex, isoDay, parseDay, pctOk, windowTotals, type WindowRow } from "@/lib/analytics/window";
import { C } from "@/lib/chart-colors";
import { inAsia } from "@/lib/area";
import { download, safeName, toCsv } from "@/lib/csv";
import { useAsmc, useDaily } from "@/lib/data/queries";
import type { MonthlySeries } from "@/lib/data/types";
import { formatCompact, formatDay, formatInt } from "@/lib/format";

function yearLabel(r: WindowRow): string {
  const s = Number(r.start.slice(0, 4));
  const e = Number(r.end.slice(0, 4));
  return s === e ? String(e) : `${s}/${String(e % 100).padStart(2, "0")}`;
}

/** Any date range compared with the same dates in every other year (app.py "Selected dates"). */
export function DatesView({
  listedId,
  series,
  lastDay,
  name,
}: {
  listedId: string | undefined;
  series: MonthlySeries;
  lastDay: string;
  name: string;
}) {
  const { data: daily, isLoading } = useDaily(listedId);
  const { data: asmc } = useAsmc();
  const { lookup, id } = useCurrentArea();
  const asia = inAsia(lookup, id);
  const dates = useExplorer((s) => s.dates);
  const setDates = useExplorer((s) => s.setDates);
  const [d0, d1] = dates ?? [isoDay(parseDay(lastDay) - 29 * 86_400_000), lastDay];

  const result = useMemo(() => {
    if (!daily) return null;
    try {
      const rows = windowTotals(series, new DailyIndex(daily), d0, d1, lastDay);
      return { rows, cmp: compareWindow(rows, Number(d1.slice(0, 4))) };
    } catch (e) {
      return { error: (e as Error).message };
    }
  }, [daily, series, d0, d1, lastDay]);

  if (!listedId) return <Empty>Date ranges are available for listed areas (not for drawn areas yet).</Empty>;

  const links = (() => {
    if (!asmc || !asia) return [];
    const out: [string, string][] = [];
    for (let t = Date.UTC(Number(d0.slice(0, 4)), Number(d0.slice(5, 7)) - 1, 1); t <= parseDay(d1); ) {
      const d = new Date(t);
      out.push(...(asmc[isoDay(t).slice(0, 7)] ?? []));
      t = Date.UTC(d.getUTCFullYear(), d.getUTCMonth() + 1, 1);
    }
    return out.slice(0, 6);
  })();

  const presets: [string, [string, string]][] = [
    ["Last 30 days", [isoDay(parseDay(lastDay) - 29 * 86_400_000), lastDay]],
    [asia ? "Haze season (Aug–Oct)" : "Aug–Oct", [`${lastDay.slice(0, 4)}-08-01`, `${lastDay.slice(0, 4)}-10-31`]],
    ["This year so far", [`${lastDay.slice(0, 4)}-01-01`, lastDay]],
  ];

  return (
    <div className="space-y-5">
      <Section title="Choose dates" description={`Any range up to one year, ending on or before ${formatDay(lastDay)}.`}>
        <div className="flex flex-wrap items-end gap-2">
          <label className="space-y-1 text-xs text-muted-foreground">
            From
            <Input type="date" value={d0} max={d1} onChange={(e) => e.target.value && setDates([e.target.value, d1])} className="h-8 w-[150px]" />
          </label>
          <label className="space-y-1 text-xs text-muted-foreground">
            To
            <Input type="date" value={d1} min={d0} max={lastDay} onChange={(e) => e.target.value && setDates([d0, e.target.value])} className="h-8 w-[150px]" />
          </label>
        </div>
        <div className="flex flex-wrap gap-1.5">
          {presets.map(([label, range]) => (
            <Button key={label} size="xs" variant="secondary" onClick={() => setDates(range)}>
              {label}
            </Button>
          ))}
        </div>
      </Section>

      {isLoading && <div className="h-48 animate-pulse rounded-xl bg-muted" />}
      {result && "error" in result && <Callout tone="warn">{result.error}.</Callout>}
      {result && "rows" in result && !result.cmp && <Callout>No complete data for these dates. Pick dates up to {formatDay(lastDay)}.</Callout>}
      {result && "rows" in result && result.cmp && (
        <Section
          title={
            <>
              {formatDay(d0)} – {formatDay(d1)}: {formatInt(result.cmp.total)} fire days
              {result.cmp.estimated && (
                <span className="font-normal text-muted-foreground">
                  {" "}
                  (estimate, likely {formatInt(result.cmp.lower)}–{formatInt(result.cmp.upper)})
                </span>
              )}
            </>
          }
          description={
            pctOk(result.cmp) ? (
              <>
                <b>
                  {Math.abs(Math.round(result.cmp.pctVsMedian!))} % {result.cmp.pctVsMedian! > 0 ? "more" : "less"} fire
                </b>{" "}
                than the median of the same dates in every other year ({formatInt(result.cmp.median)}). Rank{" "}
                <b>
                  #{result.cmp.rank} of {result.cmp.nYears}
                </b>{" "}
                (#1 = most fire).
              </>
            ) : (
              <>
                Few fires on these dates in most years (median {formatInt(result.cmp.median)}), too few for a fair %
                comparison. Rank <b>#{result.cmp.rank} of {result.cmp.nYears}</b>.
              </>
            )
          }
          action={
            <Button
              size="xs"
              variant="outline"
              onClick={() =>
                download(
                  `dates_${safeName(name)}_${d0}_${d1}.csv`,
                  toCsv(
                    ["period", "start", "end", "total", "lower", "upper", "estimated"],
                    result.rows.map((r) => [yearLabel(r), r.start, r.end, r.total.toFixed(1), r.lower.toFixed(1), r.upper.toFixed(1), r.estimated]),
                  ),
                )
              }
            >
              <Download /> CSV
            </Button>
          }
        >
          <ChartContainer config={{}} className="aspect-[16/10] w-full">
            <BarChart
              data={result.rows.map((r) => ({
                label: yearLabel(r),
                total: r.total,
                range: [r.total - r.lower, r.upper - r.total],
                lower: r.lower,
                upper: r.upper,
                est: r.estimated,
                target: r.year === result.cmp!.year,
              }))}
              margin={{ top: 14, right: 4, left: 0, bottom: 0 }}
            >
              <CartesianGrid vertical={false} strokeDasharray="3 3" />
              <XAxis dataKey="label" tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={16} />
              <YAxis tickLine={false} axisLine={false} width={40} tickFormatter={(v) => formatCompact(v)} />
              <ReferenceLine y={result.cmp.median} stroke={C.typical} strokeDasharray="5 4" label={{ value: "median", position: "insideTopLeft", fontSize: 10, fill: "currentColor" }} />
              <ChartTooltip
                cursor={{ fillOpacity: 0.3 }}
                content={({ active, payload }) => {
                  const d = active && payload?.[0]?.payload;
                  return d ? (
                    <div className="rounded-md border bg-popover/95 px-2.5 py-1.5 text-xs shadow-lg">
                      <div className="font-medium">{d.label}</div>
                      <div className="tabular-nums">{formatInt(d.total)} fire days</div>
                      <div className="text-muted-foreground">likely {formatInt(d.lower)}–{formatInt(d.upper)}</div>
                    </div>
                  ) : null;
                }}
              />
              <Bar dataKey="total" radius={[2, 2, 0, 0]} isAnimationActive={false}>
                {result.rows.map((r) => (
                  <Cell key={r.year} fill={r.year === result.cmp!.year ? C.highlight : r.estimated ? C.estimated : C.measured} />
                ))}
                <ErrorBar dataKey="range" width={0} strokeWidth={1} stroke="currentColor" className="text-foreground/50" />
              </Bar>
            </BarChart>
          </ChartContainer>
          <Note>
            Dark red = {result.cmp.year}. Light bars are estimates from older satellites (lines = 90 % likely range). Each
            converted month is split by the share of that satellite&apos;s own detections that fall on these dates.
          </Note>
        </Section>
      )}

      {links.length > 0 && (
        <Section title="What happened, in words" description="ASEAN Specialised Meteorological Centre reviews for these months.">
          <div className="flex flex-wrap gap-1.5">
            {links.map(([t, u]) => (
              <a key={u} href={u} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-muted">
                {t.replace("Review of ", "").replace(" Situation", "")} <ExternalLink className="size-3" />
              </a>
            ))}
          </div>
        </Section>
      )}
    </div>
  );
}
