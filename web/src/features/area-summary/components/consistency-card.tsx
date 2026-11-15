"use client";

import { ArrowRight, CircleCheck, TriangleAlert } from "lucide-react";
import { useMemo } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts";

import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { useExplorer } from "@/features/explorer/store";
import { C } from "@/lib/chart-colors";
import type { AnnualSeries, AreaExtraDetail } from "@/lib/data/types";
import { formatCompact, formatInt } from "@/lib/format";
import { cn } from "@/lib/utils";

import { consistency, naiveAnnual, niceTicks, signedPct } from "../lib/consistency";

const NAIVE = "#94a3b8";
const SWITCHES = [
  { x: 2002, label: "Aqua" },
  { x: 2012, label: "VIIRS" },
  { x: 2018, label: "NOAA-20" },
];

/**
 * "Is this record consistent across satellites?": the proof that the harmonization removed the false jumps,
 * shown on the Overview so it is not buried in the Method tab. Every figure comes from the exported pipeline
 * results (seam tests vs placebo steps, naive 2012 step, independent checks).
 */
export function ConsistencyCard({ annual, extra }: { annual: AnnualSeries; extra: AreaExtraDetail }) {
  const setTab = useExplorer((s) => s.setTab);
  const c = useMemo(() => consistency(extra), [extra]);
  const data = useMemo(() => {
    const naive = naiveAnnual(extra.raw, annual.years);
    return annual.years.map((y, i) => ({ year: y, harmonized: annual.total[i], naive: naive[i] }));
  }, [annual, extra.raw]);

  const ok = c.nUnusual === 0;
  const check =
    extra.official?.spearman != null
      ? { value: extra.official.spearman.toFixed(2), label: "Agreement with official burned area", hint: "rank correlation of years, 1 = same order" }
      : extra.gfed?.rMonthly != null
        ? { value: `r = ${extra.gfed.rMonthly.toFixed(2)}`, label: "Agreement with NASA GFED5 burned area", hint: "month by month, independent source" }
        : null;
  const ticks = useMemo(() => niceTicks(Math.max(0, ...data.map((d) => Math.max(d.harmonized ?? 0, d.naive ?? 0)))), [data]);

  return (
    <section aria-labelledby="consistency-title" className="scroll-mt-14 overflow-hidden rounded-xl border bg-card/60">
      <div className="flex items-start justify-between gap-3 px-3.5 pt-3">
        <div className="space-y-0.5">
          <h3 id="consistency-title" className="text-sm font-semibold tracking-tight">
            One consistent record across five satellites
          </h3>
          <p className="text-xs leading-relaxed text-muted-foreground">
            Newer satellites see far more small fires. Joined as they are, the record jumps when they change; converted to
            NOAA-20 terms, it does not.
          </p>
        </div>
        <span
          className={cn(
            "inline-flex shrink-0 items-center gap-1 rounded-full border px-2 py-0.5 text-[11px] font-medium",
            ok ? "border-emerald-600/30 bg-emerald-600/10 text-emerald-700 dark:text-emerald-400" : "border-amber-500/40 bg-amber-500/10 text-amber-700 dark:text-amber-400",
          )}
        >
          {ok ? <CircleCheck className="size-3" /> : <TriangleAlert className="size-3" />}
          {ok ? "No false jumps" : `Check ${c.nUnusual} change${c.nUnusual > 1 ? "s" : ""}`}
        </span>
      </div>

      <div className="px-2 pt-2">
        <ChartContainer config={{}} className="aspect-[16/7] w-full">
          <LineChart data={data} margin={{ top: 14, right: 10, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} strokeDasharray="3 3" />
            <XAxis dataKey="year" type="number" domain={["dataMin", "dataMax"]} ticks={[2005, 2010, 2015, 2020, 2025]} tickLine={false} axisLine={false} />
            <YAxis tickLine={false} axisLine={false} width={40} domain={[0, ticks[ticks.length - 1]]} ticks={ticks} tickFormatter={(v) => formatCompact(v)} />
            {SWITCHES.map((s) => (
              <ReferenceLine
                key={s.x}
                x={s.x}
                stroke="currentColor"
                strokeOpacity={0.25}
                strokeDasharray="2 3"
                label={{ value: s.label, position: "top", fontSize: 9, fill: "var(--muted-foreground)" }}
              />
            ))}
            <ChartTooltip
              content={({ active, payload }) => {
                const d = active && payload?.[0]?.payload;
                return d ? (
                  <div className="rounded-md border bg-popover/95 px-2.5 py-1.5 text-xs shadow">
                    <div className="font-medium">{d.year}</div>
                    <div>Harmonized: {formatInt(d.harmonized)}</div>
                    <div className="text-muted-foreground">Satellites joined as they are: {formatInt(d.naive)}</div>
                  </div>
                ) : null;
              }}
            />
            <Line dataKey="naive" stroke={NAIVE} strokeWidth={1.75} strokeDasharray="5 3" dot={false} isAnimationActive={false} connectNulls={false} />
            <Line dataKey="harmonized" stroke={C.measured} strokeWidth={2.25} dot={false} isAnimationActive={false} />
          </LineChart>
        </ChartContainer>
        <div className="flex flex-wrap gap-x-4 gap-y-1 px-1.5 pb-1 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1.5">
            <span className="h-0.5 w-4 rounded" style={{ background: C.measured }} /> Harmonized (NOAA-20 terms)
          </span>
          <span className="flex items-center gap-1.5">
            <span className="h-0 w-4 border-t-2 border-dashed" style={{ borderColor: NAIVE }} /> Satellites joined as they are
          </span>
          <span>fire days per year</span>
        </div>
      </div>

      <dl className="divide-y border-t text-xs">
        <Row label="Step at the 2012 switch to VIIRS" hint="naive → harmonized">
          <span className="text-muted-foreground line-through decoration-1">{signedPct(c.naive2012)}</span>
          <ArrowRight className="size-3 text-muted-foreground" />
          <span className="font-semibold text-foreground">{signedPct(c.harmonized2012)}</span>
        </Row>
        <Row label="Satellite changes that look like ordinary year-to-year change" hint="vs steps at dates with no change">
          <span className="font-semibold text-foreground">
            {c.seams.length - c.nUnusual} of {c.seams.length}
          </span>
        </Row>
        <Row label={check ? check.label : "Independent check"} hint={check ? check.hint : undefined}>
          {check ? <span className="font-semibold text-foreground">{check.value}</span> : <span className="text-muted-foreground">not available here</span>}
        </Row>
      </dl>

      {!ok && (
        <p className="border-t bg-amber-500/5 px-3.5 py-2 text-[11px] leading-relaxed text-muted-foreground">
          {c.seams
            .filter((s) => s.unusual)
            .map((s) => `${s.label}: ${signedPct(s.stepPct)}, bigger than ${Math.round((s.placebo ?? 0) * 100)} % of ordinary year-to-year changes here`)
            .join("; ")}
          . It may be a real change in fire (e.g. an El Niño year) or a leftover satellite effect: compare with nearby areas.
        </p>
      )}

      <button
        type="button"
        onClick={() => setTab("method")}
        className="flex w-full items-center justify-between border-t px-3.5 py-2 text-xs font-medium hover:bg-muted/60"
      >
        How it was converted and tested
        <ArrowRight className="size-3.5" />
      </button>
    </section>
  );
}

function Row({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 px-3.5 py-2">
      <dt className="min-w-0">
        <span>{label}</span>
        {hint && <span className="block text-[11px] text-muted-foreground">{hint}</span>}
      </dt>
      <dd className="flex shrink-0 items-center gap-1.5 text-sm tabular-nums">{children}</dd>
    </div>
  );
}
