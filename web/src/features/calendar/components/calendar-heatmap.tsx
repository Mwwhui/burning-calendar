"use client";

import { MapPin } from "lucide-react";
import { useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { anomalyZ, toGrid } from "@/lib/analytics/series";
import type { MonthlySeries } from "@/lib/data/types";
import { formatCompact, formatInt, MONTHS_LONG, MONTHS_SHORT } from "@/lib/format";
import { cn } from "@/lib/utils";

/** baseline of the "unusual months" view (app.py ANOMALY_BASE) */
export const ANOMALY_BASE: [number, number] = [2003, 2022];

type Mode = "amount" | "anomaly";
type Span = "recent" | "all";

interface Cell {
  key: string;
  year: number;
  month: number; // 0-11
  value: number;
  lower: number | null;
  upper: number | null;
  estimated: boolean;
  source: string;
  z: number | null;
  partial: boolean;
}

/*
 * Design (see docs/decisions.md): 300+ cells is too many for numbers in cells, so the grid shows
 * colour only, in a few labelled steps; exact values go in one details box. Rows are grouped by
 * the satellite they come from instead of hatching, with a typical-season profile on top and
 * each year's total on the right.
 */

// ---------------------------------------------------------------- colour steps
const AMOUNT_COLORS = ["#fff5d6", "#fee391", "#fec44f", "#fe9929", "#ec7014", "#cc4c02", "#8c2d04"];
const ANOMALY_STEPS = [
  { min: -Infinity, max: -2, label: "much less", color: "#2166ac" },
  { min: -2, max: -1, label: "less", color: "#92c5de" },
  { min: -1, max: 1, label: "usual", color: "#ececec" },
  { min: 1, max: 2, label: "more", color: "#f4a582" },
  { min: 2, max: Infinity, label: "much more", color: "#b2182b" },
];

/** Round a bin edge to a readable number (1, 2, 5 × 10^k). */
function nice(x: number): number {
  if (x <= 0) return 0;
  const p = 10 ** Math.floor(Math.log10(x));
  const m = x / p;
  return (m < 1.5 ? 1 : m < 3.5 ? 2 : m < 7.5 ? 5 : 10) * p;
}

/** Log-spaced, nicely rounded edges between 1 and the maximum: 7 colour steps. */
export function amountEdges(max: number): number[] {
  if (!(max > 1)) return [0, 1, 2, 3, 4, 5, 6];
  const edges = [0];
  for (let k = 1; k < AMOUNT_COLORS.length; k++) {
    const e = nice(10 ** ((Math.log10(max) * k) / AMOUNT_COLORS.length));
    edges.push(Math.max(e, edges[edges.length - 1] + 1));
  }
  return edges;
}

function amountStep(v: number, edges: number[]): number {
  let i = 0;
  while (i + 1 < edges.length && v >= edges[i + 1]) i++;
  return i;
}

function anomalyStep(z: number) {
  return ANOMALY_STEPS.find((s) => z >= s.min && z < s.max) ?? ANOMALY_STEPS[2];
}

/** Which era a year belongs to, from the satellites its months come from. */
function eraOf(sources: string[]): "measured" | "snpp" | "modis" {
  const measured = sources.filter((s) => s.endsWith("measured")).length;
  if (measured >= sources.length / 2) return "measured";
  return sources.some((s) => s.startsWith("SNPP")) ? "snpp" : "modis";
}

const ERA_LABEL = {
  measured: "Measured by NOAA-20",
  snpp: "Converted from Suomi NPP",
  modis: "Converted from MODIS (Terra / Aqua)",
};

export function CalendarHeatmap({
  series,
  partialMonth,
  enso,
  activeYear,
  onPickYear,
  onShowMonth,
  initialSpan = "recent",
  printMode = false,
}: {
  series: MonthlySeries;
  partialMonth: string | null;
  enso: Record<string, string>;
  activeYear?: number;
  onPickYear?: (year: number) => void;
  /** show a month on the map (playback, month step) when it is in the month frames */
  onShowMonth?: (month: string) => void;
  /** "all" for the printed report */
  initialSpan?: Span;
  /** hide the controls and the details box (printed report) */
  printMode?: boolean;
}) {
  const [mode, setMode] = useState<Mode>("amount");
  const [span, setSpan] = useState<Span>(initialSpan);
  const [hover, setHover] = useState<Cell | null>(null);
  const [pinned, setPinned] = useState<Cell | null>(null);

  const model = useMemo(() => {
    const z = anomalyZ(toGrid(series.months, series.value), ANOMALY_BASE);
    const cells = new Map<string, Cell>();
    const byYear = new Map<number, Cell[]>();
    let max = 0;
    series.months.forEach((m, i) => {
      const v = series.value[i];
      if (v === null) return;
      const year = Number(m.slice(0, 4));
      const month = Number(m.slice(5, 7)) - 1;
      const partial = m === partialMonth;
      const c: Cell = {
        key: m,
        year,
        month,
        value: v,
        lower: series.lower[i],
        upper: series.upper[i],
        estimated: series.estimated[i],
        source: series.source[i],
        z: partial ? null : (z.get(year)?.[month] ?? null),
        partial,
      };
      cells.set(m, c);
      byYear.set(year, [...(byYear.get(year) ?? []), c]);
      if (!partial) max = Math.max(max, v);
    });
    const years = [...byYear.keys()].sort((a, b) => b - a);
    // typical season: mean of each month over complete years
    const complete = years.filter((y) => byYear.get(y)!.filter((c) => !c.partial).length === 12);
    const profile = MONTHS_SHORT.map((_, mi) => {
      const xs = complete.map((y) => byYear.get(y)!.find((c) => c.month === mi)!.value);
      return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
    });
    const totals = new Map(years.map((y) => [y, byYear.get(y)!.reduce((a, c) => a + c.value, 0)]));
    const eras = new Map(years.map((y) => [y, eraOf(byYear.get(y)!.map((c) => c.source))]));
    return { cells, years, max, profile, totals, eras, complete: new Set(complete) };
  }, [series, partialMonth]);

  const edges = useMemo(() => amountEdges(model.max), [model.max]);
  const years = span === "recent" ? model.years.slice(0, 10) : model.years;
  const latest = model.cells.get(series.months[series.months.length - 1]) ?? null;
  const shown = hover ?? pinned ?? latest;
  const maxProfile = Math.max(1, ...model.profile);
  const maxTotal = Math.max(1, ...years.filter((y) => model.complete.has(y)).map((y) => model.totals.get(y)!));

  function colour(c: Cell): string {
    if (mode === "amount") return AMOUNT_COLORS[amountStep(c.value, edges)];
    return c.z === null ? "var(--muted)" : anomalyStep(c.z).color;
  }

  return (
    <div className="space-y-3">
      {/* controls */}
      <div className={cn("flex flex-wrap items-center justify-between gap-2", printMode && "hidden")}>
        <ToggleGroup size="sm" variant="outline" spacing={0} value={[mode]} onValueChange={(v) => v[0] && setMode(v[0] as Mode)}>
          <ToggleGroupItem value="amount" className="px-3">Amount of fire</ToggleGroupItem>
          <ToggleGroupItem value="anomaly" className="px-3">Compared with usual</ToggleGroupItem>
        </ToggleGroup>
        <ToggleGroup size="sm" variant="outline" spacing={0} value={[span]} onValueChange={(v) => v[0] && setSpan(v[0] as Span)}>
          <ToggleGroupItem value="recent" className="px-2.5">Last 10 years</ToggleGroupItem>
          <ToggleGroupItem value="all" className="px-2.5">All years</ToggleGroupItem>
        </ToggleGroup>
      </div>

      {/* details of one month */}
      {shown && !printMode && <Details c={shown} mode={mode} profile={model.profile} pinned={!!pinned && shown === pinned} onShowMonth={onShowMonth} />}

      {/* grid */}
      <div className="grid grid-cols-[2.6rem_repeat(12,minmax(0,1fr))_4.2rem] gap-x-[3px] gap-y-[3px] text-[10px]" onMouseLeave={() => setHover(null)}>
        {/* typical season profile */}
        <div className="self-end pb-0.5 text-[9px] leading-tight text-muted-foreground">usual season</div>
        {model.profile.map((p, mi) => (
          <div key={`p${mi}`} className="flex h-7 items-end" title={`${MONTHS_LONG[mi]}: about ${formatInt(p)} fire days in a typical year`}>
            <div className="w-full rounded-t-[2px] bg-orange-400/70" style={{ height: `${Math.max(4, (p / maxProfile) * 100)}%` }} />
          </div>
        ))}
        <div />
        {/* month labels */}
        <div />
        {MONTHS_SHORT.map((m) => (
          <div key={m} className="text-center font-medium text-muted-foreground">
            {m[0]}
            <span className="hidden @[400px]:inline">{m.slice(1)}</span>
          </div>
        ))}
        <div className="text-right font-medium text-muted-foreground">year</div>

        {years.map((y, k) => {
          const era = model.eras.get(y)!;
          // section header where the satellite era changes
          const header = k === 0 || era !== model.eras.get(years[k - 1]);
          const e = enso[String(y)];
          const total = model.totals.get(y)!;
          const complete = model.complete.has(y);
          return (
            <Row key={y}>
              {header && (
                <div className="col-span-full mt-1.5 flex items-center gap-2 text-[10px] font-medium text-muted-foreground first:mt-0">
                  <span>{ERA_LABEL[era]}</span>
                  <span className="h-px flex-1 bg-border" />
                  {era !== "measured" && <span className="font-normal">estimates with a likely range</span>}
                </div>
              )}
              <button
                type="button"
                onClick={() => onPickYear?.(y)}
                className={cn(
                  "flex h-[22px] items-center gap-1 rounded-[3px] pl-0.5 text-left tabular-nums hover:bg-muted",
                  y === activeYear && "bg-orange-500/15 font-semibold",
                )}
                title={`${y}${e ? ` · ${e} year` : ""} — show on the map`}
              >
                {y}
                {e && <span className={cn("size-1.5 shrink-0 rounded-full", e === "El Niño" ? "bg-red-500" : "bg-sky-500")} />}
              </button>
              {MONTHS_SHORT.map((_, mi) => {
                const key = `${y}-${String(mi + 1).padStart(2, "0")}`;
                const c = model.cells.get(key);
                if (!c) return <div key={key} className="h-[22px] rounded-[3px] bg-muted/30" />;
                const isShown = !printMode && shown?.key === key;
                return (
                  <button
                    key={key}
                    type="button"
                    aria-label={`${MONTHS_LONG[mi]} ${y}`}
                    onMouseEnter={() => setHover(c)}
                    onFocus={() => setHover(c)}
                    onClick={() => setPinned(pinned?.key === key ? null : c)}
                    className={cn(
                      "h-[22px] rounded-[3px] transition-transform hover:scale-110 hover:shadow focus-visible:outline-2 focus-visible:outline-foreground",
                      c.partial && "outline-1 -outline-offset-1 outline-foreground/70 outline-dashed",
                      isShown && "ring-2 ring-foreground ring-offset-1 ring-offset-background",
                    )}
                    style={{ backgroundColor: colour(c) }}
                  />
                );
              })}
              <div className="flex h-[22px] items-center gap-1" title={`${y}: ${formatInt(total)} fire days${complete ? "" : " so far"}`}>
                <div className="h-2 rounded-full bg-foreground/25" style={{ width: `${Math.min(100, (total / maxTotal) * 70)}%` }} />
                <span className="text-[9.5px] text-muted-foreground tabular-nums">{formatCompact(total)}</span>
              </div>
            </Row>
          );
        })}
      </div>

      {/* legend */}
      <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 text-[10.5px] text-muted-foreground">
        {mode === "amount" ? (
          <span className="flex items-center gap-1">
            <span>Fire days</span>
            {AMOUNT_COLORS.map((c, i) => (
              <span key={c} className="flex flex-col items-center">
                <span className="h-2.5 w-6 rounded-[2px]" style={{ background: c }} />
                <span className="tabular-nums">{i === 0 ? "0" : formatCompact(edges[i])}</span>
              </span>
            ))}
          </span>
        ) : (
          <span className="flex items-center gap-1">
            {ANOMALY_STEPS.map((s) => (
              <span key={s.label} className="flex items-center gap-1 pr-1.5">
                <span className="h-2.5 w-4 rounded-[2px]" style={{ background: s.color }} />
                {s.label}
              </span>
            ))}
            <span>(vs the same month in {ANOMALY_BASE[0]}–{ANOMALY_BASE[1]})</span>
          </span>
        )}
        <span className="flex items-center gap-1">
          <span className="inline-block h-2.5 w-4 rounded-[2px] outline-1 -outline-offset-1 outline-foreground/70 outline-dashed" /> month so far
        </span>
        <span className="flex items-center gap-1">
          <span className="size-1.5 rounded-full bg-red-500" /> El Niño <span className="ml-1 size-1.5 rounded-full bg-sky-500" /> La Niña
        </span>
      </div>
    </div>
  );
}

/** Rows are flat grid children; this keeps the JSX readable. */
function Row({ children }: { children: React.ReactNode }) {
  return <>{children}</>;
}

function usualWords(z: number | null): string | null {
  if (z === null) return null;
  return anomalyStep(z).label === "usual" ? "about usual for the month" : `${anomalyStep(z).label} fire than usual for the month`;
}

function Details({
  c,
  mode,
  profile,
  pinned,
  onShowMonth,
}: {
  c: Cell;
  mode: Mode;
  profile: number[];
  pinned: boolean;
  onShowMonth?: (month: string) => void;
}) {
  const usual = profile[c.month];
  const ratio = usual > 0 ? c.value / usual : null;
  const words = usualWords(c.z);
  return (
    <div className="flex items-start justify-between gap-3 rounded-xl border bg-card/60 px-3 py-2.5">
      <div className="min-w-0">
        <div className="text-[11px] text-muted-foreground">
          {MONTHS_LONG[c.month]} {c.year}
          {c.partial && " · not finished yet"}
          {pinned && " · pinned (click again to unpin)"}
        </div>
        <div className="text-lg font-semibold tabular-nums">
          {formatInt(c.value)} fire days
          {ratio !== null && !c.partial && (
            <span className="ml-2 text-sm font-normal text-muted-foreground">
              {ratio >= 1.05 ? `${ratio.toFixed(1)}× a typical ${MONTHS_SHORT[c.month]}` : ratio <= 0.95 ? `${Math.round(ratio * 100)} % of a typical ${MONTHS_SHORT[c.month]}` : `like a typical ${MONTHS_SHORT[c.month]}`}
            </span>
          )}
        </div>
        <div className="text-[11px] text-muted-foreground">
          {c.estimated && c.lower !== null && c.upper !== null
            ? `Estimate from ${c.source.split(" ")[0].replace("+", " + ")}, likely ${formatInt(c.lower)}–${formatInt(c.upper)}`
            : "Measured by NOAA-20"}
          {mode === "anomaly" && words ? ` · ${words}` : ""}
        </div>
      </div>
      {onShowMonth && (
        <Button size="xs" variant="outline" className="shrink-0" onClick={() => onShowMonth(c.key)}>
          <MapPin /> Map
        </Button>
      )}
    </div>
  );
}
