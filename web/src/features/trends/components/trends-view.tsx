"use client";

import { useMemo } from "react";
import { Bar, BarChart, CartesianGrid, Cell, ErrorBar, Line, LineChart, XAxis, YAxis } from "recharts";

import { Note, Section } from "@/components/common/section";
import { ChartContainer, ChartTooltip, type ChartConfig } from "@/components/ui/chart";
import { completeMonths, cumulativeByYear, median, toGrid } from "@/lib/analytics/series";
import { C } from "@/lib/chart-colors";
import type { AnnualSeries, MonthlySeries, Summary } from "@/lib/data/types";
import { formatCompact, formatInt, formatPct, MONTHS_SHORT, ordinal } from "@/lib/format";

function TooltipBox({ children }: { children: React.ReactNode }) {
  return <div className="rounded-md border bg-popover/95 px-2.5 py-1.5 text-xs shadow-lg backdrop-blur">{children}</div>;
}

/** How fast fire added up this year vs every other year (app.py "season" tab). */
export function CumulativeChart({ series, summary, enso }: { series: MonthlySeries; summary: Summary; enso: Record<string, string> }) {
  const { rows, others, worst, thisYear } = useMemo(() => {
    const { months, values } = completeMonths(series, summary.partialMonth);
    const cum = cumulativeByYear(toGrid(months, values));
    const thisYear = summary.thisYear;
    const totals = [...cum.entries()]
      .filter(([y]) => y !== thisYear)
      .map(([y, r]) => ({ y, t: Math.max(...r.map((v) => v ?? 0)) }))
      .sort((a, b) => b.t - a.t);
    const worst = totals.slice(0, 3).map((x) => x.y);
    const others = [...cum.keys()].filter((y) => y !== thisYear && !worst.includes(y));
    const rows = MONTHS_SHORT.map((m, mi) => {
      const r: Record<string, number | string | null> = { month: m };
      const typical: number[] = [];
      for (const [y, vals] of cum) {
        r[`y${y}`] = vals[mi];
        if (y !== thisYear && vals[mi] !== null) typical.push(vals[mi]!);
      }
      r.typical = typical.length ? median(typical) : null;
      return r;
    });
    return { rows, others, worst, thisYear };
  }, [series, summary]);

  const config: ChartConfig = {};
  return (
    <Section
      title="Fire added up through the year"
      description={
        <>
          {thisYear} so far ranks <b>{ordinal(summary.rank)} of {summary.nYears}</b> ({formatPct(summary.pctVsMedian)} vs a
          typical year). Coloured: the three biggest fire years.
        </>
      }
    >
      <ChartContainer config={config} className="aspect-[4/3] w-full">
        <LineChart data={rows} margin={{ top: 6, right: 8, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" />
          <XAxis dataKey="month" tickLine={false} axisLine={false} interval={1} />
          <YAxis tickLine={false} axisLine={false} width={40} tickFormatter={(v) => formatCompact(v)} />
          <ChartTooltip
            content={({ active, label, payload }) =>
              active && payload?.length ? (
                <TooltipBox>
                  <div className="mb-0.5 font-medium">Up to end of {label}</div>
                  {payload
                    .filter((p) => ["typical", `y${thisYear}`, ...worst.map((w) => `y${w}`)].includes(String(p.dataKey)))
                    .map((p) => (
                      <div key={String(p.dataKey)} className="flex justify-between gap-4">
                        <span style={{ color: p.color }}>{p.name}</span>
                        <span className="tabular-nums">{formatInt(p.value as number)}</span>
                      </div>
                    ))}
                </TooltipBox>
              ) : null
            }
          />
          {others.map((y) => (
            <Line key={y} dataKey={`y${y}`} name={String(y)} stroke={C.neutral} strokeOpacity={0.35} strokeWidth={1} dot={false} isAnimationActive={false} />
          ))}
          <Line dataKey="typical" name="Typical year" stroke={C.typical} strokeDasharray="5 4" strokeWidth={2} dot={false} isAnimationActive={false} />
          {worst.map((y, i) => (
            <Line key={y} dataKey={`y${y}`} name={`${y}${enso[String(y)] ? ` (${enso[String(y)]})` : ""}`} stroke={C.rank[i]} strokeWidth={2} dot={false} isAnimationActive={false} />
          ))}
          <Line dataKey={`y${thisYear}`} name={`${thisYear} (so far)`} stroke={C.highlight} strokeWidth={3.5} dot={{ r: 2.5 }} isAnimationActive={false} connectNulls={false} />
        </LineChart>
      </ChartContainer>
      <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px]">
        <Legend color={C.highlight} label={`${thisYear} so far`} thick />
        <Legend color={C.typical} label="Typical year" dashed />
        {worst.map((y, i) => (
          <Legend key={y} color={C.rank[i]} label={`${y}${enso[String(y)] ? ` · ${enso[String(y)]}` : ""}`} />
        ))}
        <Legend color={C.neutral} label="Other years" />
      </div>
    </Section>
  );
}

function Legend({ color, label, thick, dashed }: { color: string; label: string; thick?: boolean; dashed?: boolean }) {
  return (
    <span className="flex items-center gap-1.5 text-muted-foreground">
      <span
        className="inline-block w-4"
        style={{ borderTop: `${thick ? 3 : 2}px ${dashed ? "dashed" : "solid"} ${color}` }}
      />
      {label}
    </span>
  );
}

/** Yearly totals with their 90 % likely range; click a bar to show that year on the map. */
export function YearlyBars({
  annual,
  activeYear,
  onPickYear,
}: {
  annual: AnnualSeries;
  activeYear?: number;
  onPickYear?: (year: number) => void;
}) {
  const data = annual.years.map((y, i) => {
    const t = annual.total[i] ?? 0;
    return {
      year: y,
      total: t,
      range: [Math.max(0, t - (annual.lower[i] ?? t)), Math.max(0, (annual.upper[i] ?? t) - t)],
      lower: annual.lower[i],
      upper: annual.upper[i],
      est: (annual.estimatedShare[i] ?? 0) > 0,
    };
  });
  if (!data.length) return <Note>No complete years yet.</Note>;
  return (
    <Section
      title="Yearly totals"
      description="With the 90 % likely range. Bars whose ranges overlap cannot be told apart. Click a bar to show that year on the map."
    >
      <ChartContainer config={{}} className="aspect-[16/9] w-full">
        <BarChart data={data} margin={{ top: 6, right: 4, left: 0, bottom: 0 }} onClick={(s) => s?.activeLabel && onPickYear?.(Number(s.activeLabel))}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" />
          <XAxis dataKey="year" tickLine={false} axisLine={false} interval="preserveStartEnd" minTickGap={18} />
          <YAxis tickLine={false} axisLine={false} width={40} tickFormatter={(v) => formatCompact(v)} />
          <ChartTooltip
            cursor={{ fillOpacity: 0.3 }}
            content={({ active, payload }) => {
              const d = active && payload?.[0]?.payload;
              return d ? (
                <TooltipBox>
                  <div className="font-medium">{d.year}</div>
                  <div className="tabular-nums">{formatInt(d.total)} fire days</div>
                  {d.est && (
                    <div className="text-muted-foreground">
                      estimate, likely {formatInt(d.lower)}–{formatInt(d.upper)}
                    </div>
                  )}
                </TooltipBox>
              ) : null;
            }}
          />
          <Bar dataKey="total" radius={[2, 2, 0, 0]} className="cursor-pointer" isAnimationActive={false}>
            {data.map((d) => (
              <Cell key={d.year} fill={d.year === activeYear ? C.highlight : d.est ? C.estimated : C.measured} />
            ))}
            <ErrorBar dataKey="range" width={0} strokeWidth={1} stroke="currentColor" className="text-foreground/50" />
          </Bar>
        </BarChart>
      </ChartContainer>
      <Note>Light bars contain months estimated from older satellites; dark bars are measured by NOAA-20. Unfinished years are left out.</Note>
    </Section>
  );
}
