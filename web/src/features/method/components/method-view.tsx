"use client";

import { CircleCheck, ChevronDown, TriangleAlert } from "lucide-react";
import { useMemo, useState } from "react";
import { Area, CartesianGrid, ComposedChart, Line, XAxis, YAxis } from "recharts";

import { Empty, Note, Section } from "@/components/common/section";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { consistency, contest, methodName, signedPct } from "@/features/area-summary/lib/consistency";
import { C, SAT_NAME } from "@/lib/chart-colors";
import type { AreaExtraDetail, MonthlySeries } from "@/lib/data/types";
import { formatCompact, formatInt, formatPeriod } from "@/lib/format";
import { cn } from "@/lib/utils";

function pct(x: number | null | undefined) {
  return x === null || x === undefined ? "–" : `${Math.round(x * 100)} %`;
}

/** What each satellite saw vs the combined record, why they differ, and the technical steps. */
export function MethodView({ series, extra }: { series: MonthlySeries; extra: AreaExtraDetail | undefined }) {
  const data = useMemo(() => {
    if (!extra) return [];
    const idx = new Map(series.months.map((m, i) => [m, i]));
    return extra.raw.months.map((m, j) => {
      const r: Record<string, number | string | null | [number, number]> = { m };
      for (const s of extra.raw.sats) {
        const v = extra.raw.values[s][j];
        r[s] = v !== null && v > 0 ? v : null;
      }
      const i = idx.get(m);
      if (i !== undefined && series.value[i] !== null && series.value[i]! > 0) {
        r.combined = series.value[i];
        r.band = [Math.max(1, series.lower[i] ?? series.value[i]!), Math.max(1, series.upper[i] ?? series.value[i]!)];
      }
      return r;
    });
  }, [extra, series]);

  if (!extra) return <div className="h-64 animate-pulse rounded-xl bg-muted" />;
  const sats = extra.raw.sats;

  return (
    <div className="space-y-6">
      <div className="space-y-2 text-sm leading-relaxed">
        <p>
          <b>In short.</b> Five NASA satellites have watched fires since 2000, but newer ones see far more small fires
          (375 m pixels instead of 1 km). Joining their records directly makes it look as if fires jumped in 2012. So every
          month is converted to what <b>NOAA-20</b> (flying since 2018) would have seen:
        </p>
        <ol className="list-decimal space-y-0.5 pl-5 text-[13px]">
          <li><b>2018 – today:</b> NOAA-20, measured.</li>
          <li><b>2012 – 2018:</b> Suomi NPP, a twin of NOAA-20, converted (small change).</li>
          <li><b>2002 – 2011:</b> MODIS Aqua and Terra, converted and averaged (bigger change, wider ranges).</li>
          <li><b>2000 – 2002:</b> Terra alone.</li>
        </ol>
        <p className="text-xs text-muted-foreground">
          Each conversion was tested by hiding real data: the 90 % ranges contained the true value 91–98 % of the time.
        </p>
      </div>

      <Section title="What each satellite saw" description="Thin lines: raw monthly fire days per satellite. Red with band: the combined record and its likely range (log scale).">
        <ChartContainer config={{}} className="aspect-[4/3] w-full">
          <ComposedChart data={data} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
            <CartesianGrid vertical={false} strokeDasharray="3 3" />
            <XAxis dataKey="m" tickLine={false} axisLine={false} minTickGap={40} tickFormatter={(v: string) => v.slice(0, 4)} />
            <YAxis scale="log" domain={[1, "auto"]} allowDataOverflow tickLine={false} axisLine={false} width={40} tickFormatter={(v) => formatCompact(v)} />
            <ChartTooltip
              content={({ active, payload, label }) =>
                active && payload?.length ? (
                  <div className="rounded-md border bg-popover/95 px-2.5 py-1.5 text-xs shadow">
                    <div className="mb-0.5 font-medium">{formatPeriod(String(label))}</div>
                    {payload
                      .filter((p) => p.dataKey !== "band" && p.value !== null)
                      .map((p) => (
                        <div key={String(p.dataKey)} className="flex justify-between gap-3">
                          <span style={{ color: p.color }}>{p.name}</span>
                          <span className="tabular-nums">{formatInt(p.value as number)}</span>
                        </div>
                      ))}
                  </div>
                ) : null
              }
            />
            <Area dataKey="band" stroke="none" fill={C.highlight} fillOpacity={0.18} isAnimationActive={false} connectNulls={false} />
            {sats.map((s) => (
              <Line key={s} dataKey={s} name={SAT_NAME[s] ?? s} stroke={C.sat[s] ?? C.other} strokeWidth={1} dot={false} isAnimationActive={false} connectNulls={false} />
            ))}
            <Line dataKey="combined" name="Combined record" stroke={C.highlight} strokeWidth={2} dot={false} isAnimationActive={false} />
          </ComposedChart>
        </ChartContainer>
        <div className="flex flex-wrap gap-x-3 gap-y-1 text-[11px] text-muted-foreground">
          {sats.map((s) => (
            <span key={s} className="flex items-center gap-1.5">
              <span className="inline-block w-3 border-t-2" style={{ borderColor: C.sat[s] }} /> {SAT_NAME[s] ?? s}
            </span>
          ))}
          <span className="flex items-center gap-1.5">
            <span className="inline-block w-3 border-t-[3px]" style={{ borderColor: C.highlight }} /> combined
          </span>
        </div>
      </Section>

      <SeamProof extra={extra} />
      <Contest extra={extra} />

      {extra.satDiff && <SatDiffTable d={extra.satDiff} />}

      <Technical extra={extra} />
    </div>
  );
}

function SatDiffTable({ d }: { d: NonNullable<AreaExtraDetail["satDiff"]> }) {
  const t = new Map(d.rows.map((r) => [r.sat, r]));
  const mod = d.rows.filter((r) => r.sat === "Terra" || r.sat === "Aqua");
  const vi = d.rows.filter((r) => r.sat === "SNPP" || r.sat === "NOAA20");
  const avg = (xs: (number | null)[]) => xs.reduce<number>((a, b) => a + (b ?? 0), 0) / Math.max(1, xs.length);
  return (
    <Section title="Why the satellites see different amounts of fire" description={`Same area, same years (${d.years[0]}–${d.years[d.years.length - 1]}), same fires: the satellites differ only in how they look.`}>
      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-xs tabular-nums">
          <thead className="bg-muted/50 text-muted-foreground">
            <tr>
              <th className="px-2 py-1.5 text-left font-medium">Satellite</th>
              <th className="px-2 py-1.5 text-right font-medium">Detections</th>
              <th className="px-2 py-1.5 text-right font-medium">vs NOAA-20</th>
              <th className="px-2 py-1.5 text-right font-medium">At night</th>
              <th className="px-2 py-1.5 text-right font-medium">Weak (&lt;10 MW)</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {d.rows.map((r) => (
              <tr key={r.sat}>
                <td className="px-2 py-1.5">{SAT_NAME[r.sat] ?? r.sat}</td>
                <td className="px-2 py-1.5 text-right">{formatInt(r.detections)}</td>
                <td className="px-2 py-1.5 text-right">{pct(r.vsNoaa20)}</td>
                <td className="px-2 py-1.5 text-right">{pct(r.night)}</td>
                <td className="px-2 py-1.5 text-right">{pct(r.weak)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <ul className="list-disc space-y-1 pl-4 text-xs leading-relaxed">
        {mod.length > 0 && vi.length > 0 && (
          <li>
            <b>Pixel size.</b> VIIRS pixels are 375 m, MODIS 1 km. {pct(avg(vi.map((r) => r.weak)))} of VIIRS detections are
            weak fires against {pct(avg(mod.map((r) => r.weak)))} for MODIS: small fires are mostly invisible to MODIS, the
            main reason it sees only about {pct(avg(mod.map((r) => r.vsNoaa20)))} as much fire.
          </li>
        )}
        {t.has("Terra") && t.has("Aqua") && (
          <li>
            <b>Overpass time.</b> Terra passes in the morning (~10:30), Aqua and VIIRS early afternoon (~13:30), when farm
            fires peak. Terra sees {pct(t.get("Terra")!.detections / Math.max(1, t.get("Aqua")!.detections))} of what Aqua
            sees with the same instrument.
          </li>
        )}
        {t.has("NOAA20") && (
          <li>
            <b>Night.</b> VIIRS also detects many fires at night ({pct(t.get("NOAA20")!.night)} of NOAA-20 detections),
            mostly smouldering peat and lasting fires.
          </li>
        )}
        {t.has("SNPP") && t.has("NOAA20") && (
          <li>
            <b>Twins.</b> Suomi NPP and NOAA-20 carry the same instrument half an orbit apart: {pct(t.get("SNPP")!.vsNoaa20)} of
            NOAA-20, so their conversion is small.
          </li>
        )}
      </ul>
    </Section>
  );
}

function Technical({ extra }: { extra: AreaExtraDetail }) {
  const [open, setOpen] = useState(false);
  return (
    <section className="rounded-xl border">
      <button type="button" onClick={() => setOpen(!open)} className="flex w-full items-center justify-between px-3 py-2.5 text-sm font-medium">
        Technical details (for specialists)
        <ChevronDown className={cn("size-4 transition-transform", open && "rotate-180")} />
      </button>
      {open && (
        <div className="space-y-4 border-t p-3 text-xs">
          <div className="overflow-x-auto">
            <table className="w-full tabular-nums">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="pr-2 text-left font-medium">From</th>
                  <th className="pr-2 text-left font-medium">Status</th>
                  <th className="pr-2 text-left font-medium">Method</th>
                  <th className="pr-2 text-left font-medium">Fit window</th>
                  <th className="pr-2 text-right font-medium">Months</th>
                  <th className="text-right font-medium">Drift/yr</th>
                </tr>
              </thead>
              <tbody>
                {extra.steps.map((s) => (
                  <tr key={s.donor} title={s.why ?? ""} className="align-top">
                    <td className="py-1 pr-2">{s.donor}</td>
                    <td className="pr-2">{s.status}</td>
                    <td className="pr-2">{s.method ?? "–"}</td>
                    <td className="pr-2">{s.fitWindow?.map((x) => x ?? "…").join(" → ") ?? "–"}</td>
                    <td className="pr-2 text-right">{s.monthsFilled}</td>
                    <td className="text-right">{s.drift ?? "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {extra.steps
            .filter((s) => s.status === "applied" && s.loyo)
            .map((s) => (
              <div key={s.donor}>
                <div className="mb-1 font-medium">{s.donor}: leave-one-year-out scores</div>
                <table className="w-full tabular-nums">
                  <thead className="text-muted-foreground">
                    <tr>
                      <th className="text-left font-medium">Method</th>
                      <th className="text-left font-medium">Route</th>
                      <th className="text-right font-medium">RMSE(log)</th>
                      <th className="text-right font-medium">Bias %</th>
                      <th className="text-right font-medium">Years</th>
                    </tr>
                  </thead>
                  <tbody>
                    {s.loyo!.map((r, i) => (
                      <tr key={i}>
                        <td>{r.method}</td>
                        <td>{r.route ?? ""}</td>
                        <td className="text-right">{r.rmse ?? "–"}</td>
                        <td className="text-right">{r.bias ?? "–"}</td>
                        <td className="text-right">{r.years ?? ""}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {s.why && <p className="mt-1 text-muted-foreground">{s.why}</p>}
              </div>
            ))}
          <div>
            <div className="mb-1 font-medium">Seam tests</div>
            <table className="w-full tabular-nums">
              <thead className="text-muted-foreground">
                <tr>
                  <th className="text-left font-medium">Seam</th>
                  <th className="text-right font-medium">Step %</th>
                  <th className="text-right font-medium">Placebo</th>
                </tr>
              </thead>
              <tbody>
                {extra.seams.rows.map((r) => (
                  <tr key={r.seam}>
                    <td>{r.seam}</td>
                    <td className="text-right">{r.stepPct ?? "–"}</td>
                    <td className="text-right">{r.placebo ?? "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
            <p className="mt-1 text-muted-foreground">
              Step where the data source changes, compared with steps at dates where nothing changed (placebo close to 1 =
              suspicious). The naive record&apos;s 2012 step: {extra.seams.naiveStep2012 === null ? "n/a" : `${extra.seams.naiveStep2012 > 0 ? "+" : ""}${Math.round(extra.seams.naiveStep2012)} %`}.
            </p>
          </div>
          <Note>Methods: M1 constant ratio · M2 monthly ratio · M3 log-linear · M4 quantile mapping. Units: NOAA-20-equivalent fire cell-days on local solar dates.</Note>
        </div>
      )}
    </section>
  );
}

const TH = "py-1.5 pr-3 text-left text-[11px] font-medium whitespace-nowrap text-muted-foreground";

/** The seam tests in plain words: each satellite change against steps at dates when nothing changed. */
function SeamProof({ extra }: { extra: AreaExtraDetail }) {
  const c = consistency(extra);
  if (!c.seams.length) return null;
  return (
    <Section
      title="Test 1 · No false jumps when satellites change"
      description="The record is compared two years before and after each change (seasons removed), and that step is ranked among the steps at every other January, when no satellite changed. A real change in fire can be large too; a step bigger than 95 % of ordinary ones would point to a leftover satellite effect."
    >
      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-xs tabular-nums">
          <thead className="border-b bg-muted/40">
            <tr>
              <th className={cn(TH, "pl-3")}>Satellite change</th>
              <th className={cn(TH, "text-right")}>Step</th>
              <th className={cn(TH, "text-right")} title="Share of ordinary year-to-year steps that are smaller than this one">vs ordinary</th>
              <th className={cn(TH, "pr-3")}>Result</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {c.seams.map((r) => (
              <tr key={r.seam}>
                <td className="py-1.5 pr-3 pl-3 whitespace-nowrap">{r.label}</td>
                <td className="pr-3 text-right whitespace-nowrap">{signedPct(r.stepPct)}</td>
                <td className="pr-3 text-right whitespace-nowrap">{r.placebo === null ? "–" : `bigger than ${Math.round(r.placebo * 100)} %`}</td>
                <td className="pr-3 whitespace-nowrap">
                  {r.unusual ? (
                    <span className="inline-flex items-center gap-1 text-amber-700 dark:text-amber-400"><TriangleAlert className="size-3" /> check</span>
                  ) : (
                    <span className="inline-flex items-center gap-1 text-emerald-700 dark:text-emerald-400"><CircleCheck className="size-3" /> ordinary</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {c.naive2012 !== null && (
        <Note>
          For comparison, joining the satellites as they are gives a step of <b>{signedPct(c.naive2012)}</b> at the 2012 switch to VIIRS here.
        </Note>
      )}
    </Section>
  );
}

/** How each conversion was chosen: error on years hidden from the fit, method used vs the best other one. */
function Contest({ extra }: { extra: AreaExtraDetail }) {
  const rows = contest(extra.steps);
  if (!rows.length) return null;
  const pctTxt = (x: number | null) => (x === null ? "–" : `±${x < 10 ? x.toFixed(1) : Math.round(x)} %`);
  return (
    <Section
      title="Test 2 · Each conversion checked on years it never saw"
      description="Every step was fitted again with one year left out, then asked to predict that year (leave-one-year-out). The simpler method is kept unless a more complex one is clearly better on these hidden years."
    >
      <div className="overflow-x-auto rounded-xl border">
        <table className="w-full text-xs tabular-nums">
          <thead className="border-b bg-muted/40">
            <tr>
              <th className={cn(TH, "pl-3")}>Satellite</th>
              <th className={TH}>Method used</th>
              <th className={cn(TH, "text-right")}>Typical error</th>
              <th className={cn(TH, "pr-3 text-right")}>Best other</th>
            </tr>
          </thead>
          <tbody className="divide-y">
            {rows.map((r) => (
              <tr key={r.donor} className="align-top">
                <td className="py-1.5 pr-3 pl-3">{SAT_NAME[r.donor] ?? r.donor.replace("+", " + ")}</td>
                <td className="pr-3">{methodName(r.method)}</td>
                <td className="pr-3 text-right whitespace-nowrap">
                  {r.combined ? "≈ " : ""}
                  {pctTxt(r.chosenErr)}
                </td>
                <td className="pr-3 text-right whitespace-nowrap text-muted-foreground">
                  {r.runnerUp ? `${pctTxt(r.runnerUp.err)} · ${r.runnerUp.method}` : "–"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <Note>
        Typical error = monthly error on hidden years (root mean square, log scale). ≈: two routes (via Aqua and via Terra) are averaged,
        so the best single route is shown. Method codes: M0 none · M1 fixed ratio · M2 ratio per month · M3 log-linear · M4 quantile mapping.
      </Note>
    </Section>
  );
}

export function MethodUnavailable() {
  return <Empty>The method details are computed for listed areas. Your drawn area reuses its country&apos;s conversion.</Empty>;
}
