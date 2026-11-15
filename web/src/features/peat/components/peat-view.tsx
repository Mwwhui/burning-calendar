"use client";

import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { Empty, Note, Section } from "@/components/common/section";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { median } from "@/lib/analytics/series";
import { C } from "@/lib/chart-colors";
import type { PeatSplit } from "@/lib/data/types";
import { formatCompact, formatInt } from "@/lib/format";

/** Fire on mapped peat vs elsewhere (app.py "peat" tab). */
export function PeatView({ p }: { p: PeatSplit | null | undefined }) {
  if (!p) return <Empty>The peat split is not available here.</Empty>;
  if (p.tooLittle || !p.years) {
    return <Empty>Little or no mapped peat in this area{p.km2 ? ` (about ${formatInt(p.km2)} km²)` : ""}.</Empty>;
  }
  const rows = p.years.map((y, i) => ({ year: y, on: p.on![i] ?? 0, off: p.off![i] ?? 0 }));
  const shares = rows.filter((r) => r.on + r.off > 0).map((r) => ({ y: r.year, s: r.on / (r.on + r.off), t: r.on + r.off }));
  const typical = median(shares.map((x) => x.s));
  const top = shares.reduce((a, b) => (b.s > a.s ? b : a), shares[0]);
  const tMed = median(shares.map((x) => x.t));
  const big = shares.filter((x) => x.t >= tMed);
  const bigMean = big.length ? big.reduce((a, b) => a + b.s, 0) / big.length : Number.NaN;

  return (
    <div className="space-y-5">
      <p className="text-sm leading-relaxed">
        Fires on <b>peat</b> smoulder underground, burn for weeks and make most of the region&apos;s haze. This splits the
        record into fires on mapped peat and fires elsewhere; each part is converted with the same chain as the total.
        {p.km2 ? <> Mapped peat here: about <b>{formatInt(p.km2)} km²</b>.</> : null}
      </p>
      <Section title="Fire on peat and elsewhere, per year">
        <ChartContainer config={{ on: { label: "On peat", color: C.peatOn }, off: { label: "Not on peat", color: C.peatOff } }} className="aspect-[16/9] w-full">
          <BarChart data={rows} margin={{ top: 6, right: 4, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} strokeDasharray="3 3" />
            <XAxis dataKey="year" tickLine={false} axisLine={false} minTickGap={18} />
            <YAxis tickLine={false} axisLine={false} width={40} tickFormatter={(v) => formatCompact(v)} />
            <ChartTooltip
              content={({ active, payload }) => {
                const d = active && payload?.[0]?.payload;
                return d ? (
                  <div className="rounded-md border bg-popover/95 px-2.5 py-1.5 text-xs shadow">
                    <div className="font-medium">{d.year}</div>
                    <div>On peat: {formatInt(d.on)}</div>
                    <div>Elsewhere: {formatInt(d.off)}</div>
                    <div className="text-muted-foreground">{Math.round((100 * d.on) / Math.max(1, d.on + d.off))} % on peat</div>
                  </div>
                ) : null;
              }}
            />
            <Bar dataKey="on" stackId="a" fill="var(--color-on)" isAnimationActive={false} />
            <Bar dataKey="off" stackId="a" fill="var(--color-off)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
          </BarChart>
        </ChartContainer>
        <div className="flex gap-4 text-[11px] text-muted-foreground">
          <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: C.peatOn }} /> on peat</span>
          <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm" style={{ background: C.peatOff }} /> not on peat</span>
        </div>
      </Section>
      <p className="text-sm">
        Share of fire on peat: <b>{Math.round(typical * 100)} %</b> in a typical year, up to {Math.round(top.s * 100)} % ({top.y}).
        {big.length >= 3 && Math.abs(bigMean - typical) >= 0.03 && (
          <> In the bigger fire years, <b>{Math.round(bigMean * 100)} %</b> of fire was on peat.</>
        )}
      </p>
      <Note>
        The two parts are converted separately, so they add up to the total only approximately. Years before 2018 are
        estimates. Peat map: CIFOR tropical peatland map v2.1 (Gumbricht et al. 2017, CC BY 4.0), ~230 m. A ~1 km square
        counts as peat when at least half of it is mapped peat. The map also counts mangroves and over-maps peat in places,
        so read this as &ldquo;fires on mapped peat&rdquo;, not a field survey.
      </Note>
    </div>
  );
}
