/**
 * Calendar maths on a monthly series, ported from burncal.calendar and app/data.py
 * so the web app can show anomalies, season-to-date ranks and own areas without a server.
 * Each function names the Python function it mirrors; keep them in step.
 */
import type { MonthlySeries, Summary } from "@/lib/data/types";

export type YearGrid = Map<number, (number | null)[]>;

/** burncal.calendar.to_grid: year -> 12 monthly values (null = no data). */
export function toGrid(months: string[], values: (number | null)[]): YearGrid {
  const g: YearGrid = new Map();
  months.forEach((m, i) => {
    const y = Number(m.slice(0, 4));
    const mi = Number(m.slice(5, 7)) - 1;
    if (!g.has(y)) g.set(y, Array(12).fill(null));
    g.get(y)![mi] = values[i];
  });
  return new Map([...g.entries()].sort((a, b) => a[0] - b[0]));
}

function mean(xs: number[]): number {
  return xs.reduce((a, b) => a + b, 0) / xs.length;
}

/** sample standard deviation (pandas std, ddof = 1) */
function std(xs: number[]): number {
  if (xs.length < 2) return Number.NaN;
  const m = mean(xs);
  return Math.sqrt(xs.reduce((a, b) => a + (b - m) ** 2, 0) / (xs.length - 1));
}

export function median(xs: number[]): number {
  if (!xs.length) return Number.NaN;
  const s = [...xs].sort((a, b) => a - b);
  const h = Math.floor(s.length / 2);
  return s.length % 2 ? s[h] : (s[h - 1] + s[h]) / 2;
}

/** burncal.calendar.anomaly_z: z-score of log1p against the same month in the baseline years. */
export function anomalyZ(grid: YearGrid, base: [number, number]): YearGrid {
  const stats = Array.from({ length: 12 }, (_, mi) => {
    const xs: number[] = [];
    for (const [y, row] of grid) if (y >= base[0] && y <= base[1] && row[mi] !== null) xs.push(Math.log1p(row[mi]!));
    const sd = std(xs);
    return { m: xs.length ? mean(xs) : Number.NaN, sd: sd > 0 ? sd : Number.NaN };
  });
  const out: YearGrid = new Map();
  for (const [y, row] of grid) {
    out.set(
      y,
      row.map((v, mi) => {
        if (v === null) return null;
        const z = (Math.log1p(v) - stats[mi].m) / stats[mi].sd;
        return Number.isFinite(z) ? z : null;
      }),
    );
  }
  return out;
}

/** app/data.py cumulative_by_year: running total per year (null after the last month with data). */
export function cumulativeByYear(grid: YearGrid): Map<number, (number | null)[]> {
  const out = new Map<number, (number | null)[]>();
  for (const [y, row] of grid) {
    let acc = 0;
    out.set(
      y,
      row.map((v) => {
        if (v === null) return null;
        acc += v;
        return acc;
      }),
    );
  }
  return out;
}

/** Series without a still-running last month (app/data.py partial_month). */
export function completeMonths(series: MonthlySeries, partialMonth: string | null) {
  const keep = series.months.map((m) => m !== partialMonth);
  return {
    months: series.months.filter((_, i) => keep[i]),
    values: series.value.filter((_, i) => keep[i]),
  };
}

/**
 * app/data.py summary_numbers (with burncal.calendar.season_to_date) for a series built in the
 * browser (own areas). `partialMonth` is the unfinished current month, left out as in Python.
 */
export function summaryFor(series: MonthlySeries, partialMonth: string | null, busiestRange?: {
  years: number[];
  lower: (number | null)[];
  upper: (number | null)[];
  total: (number | null)[];
}): Summary | null {
  const { months, values } = completeMonths(series, partialMonth);
  const idx = values.map((v, i) => (v === null ? -1 : i)).filter((i) => i >= 0);
  if (!idx.length) return null;
  const grid = toGrid(
    idx.map((i) => months[i]),
    idx.map((i) => values[i]),
  );
  // climatology: mean of each calendar month over the years that have it
  const clim = Array.from({ length: 12 }, (_, mi) => {
    const xs = [...grid.values()].map((r) => r[mi]).filter((v): v is number => v !== null);
    return xs.length ? mean(xs) : 0;
  });
  const climSum = clim.reduce((a, b) => a + b, 0);
  const peak = clim.indexOf(Math.max(...clim));
  // complete years only for the busiest year
  let busiest: number | null = null;
  let busiestTotal = -1;
  for (const [y, row] of grid) {
    if (row.every((v) => v !== null)) {
      const t = row.reduce<number>((a, b) => a + (b ?? 0), 0);
      if (t > busiestTotal) {
        busiestTotal = t;
        busiest = y;
      }
    }
  }
  const lastMonth = months[idx[idx.length - 1]];
  const thisYear = Number(lastMonth.slice(0, 4));
  const through = Number(lastMonth.slice(5, 7));
  const toDate = new Map<number, number>();
  for (const [y, row] of grid) {
    const part = row.slice(0, through);
    if (part.every((v) => v !== null)) toDate.set(y, part.reduce<number>((a, b) => a + (b ?? 0), 0));
  }
  const cur = toDate.get(thisYear) ?? null;
  const hist = [...toDate.entries()].filter(([y]) => y !== thisYear).map(([, v]) => v);
  const med = median(hist);
  const rank = cur === null ? 0 : [...toDate.values()].filter((v) => v > cur).length + 1;
  const estYears = new Set(
    series.months.filter((_, i) => series.estimated[i] && series.value[i] !== null).map((m) => Number(m.slice(0, 4))),
  );
  let ties: number[] = [];
  if (busiestRange && busiest !== null) {
    const bi = busiestRange.years.indexOf(busiest);
    const lo = bi >= 0 ? busiestRange.lower[bi] : null;
    if (lo !== null) {
      ties = busiestRange.years
        .map((y, i) => ({ y, up: busiestRange.upper[i], t: busiestRange.total[i] ?? 0 }))
        .filter((r) => r.y !== busiest && r.up !== null && r.up >= lo)
        .sort((a, b) => b.t - a.t)
        .map((r) => r.y);
    }
  }
  return {
    peakMonth: peak + 1,
    peakShare: climSum > 0 ? clim[peak] / climSum : null,
    busiestYear: busiest,
    busiestYearTotal: busiest === null ? null : busiestTotal,
    busiestYearEstimated: busiest !== null && estYears.has(busiest),
    busiestTies: ties,
    partialMonth,
    thisYear,
    throughMonth: through,
    thisYearToDate: cur,
    rank,
    nYears: toDate.size,
    pctVsMedian: cur !== null && med > 0 ? 100 * (cur / med - 1) : null,
  };
}
