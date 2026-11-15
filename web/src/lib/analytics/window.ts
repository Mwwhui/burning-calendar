/**
 * Date-range comparison, ported from burncal.daily.window_totals / compare_window.
 *
 * The harmonized record is monthly. For a date range, each overlapped month contributes its
 * harmonized value times the share of that month's raw cell-days (from the satellite(s) the
 * month was measured or converted from) that falls inside the range.
 */
import type { DailyData, MonthlySeries } from "@/lib/data/types";

import { median } from "./series";

const DAY = 86_400_000;

export function parseDay(iso: string): number {
  const [y, m, d] = iso.split("-").map(Number);
  return Date.UTC(y, m - 1, d);
}

export function isoDay(t: number): string {
  return new Date(t).toISOString().slice(0, 10);
}

function addYears(t: number, k: number): number {
  const d = new Date(t);
  const y = d.getUTCFullYear() + k;
  const m = d.getUTCMonth();
  // pandas DateOffset(years=k): 29 Feb -> 28 Feb in non-leap years
  const last = new Date(Date.UTC(y, m + 1, 0)).getUTCDate();
  return Date.UTC(y, m, Math.min(d.getUTCDate(), last));
}

/** burncal.daily._sources: satellites of a month's source label ("Aqua+Terra converted ..."). */
export function sources(src: string): string[] {
  return src.split(" ")[0].split("+");
}

/** Dense day -> count lookups per satellite. */
export class DailyIndex {
  readonly start: number;
  private sats = new Map<string, Map<number, number>>();
  constructor(daily: DailyData) {
    this.start = parseDay(daily.start);
    for (const [sat, s] of Object.entries(daily.sats)) {
      const m = new Map<number, number>();
      s.d.forEach((d, i) => m.set(d, s.v[i]));
      this.sats.set(sat, m);
    }
  }
  has(sat: string) {
    return this.sats.has(sat);
  }
  /** sum of cell-days of the given satellites over [t0, t1] (inclusive, UTC day starts) */
  sum(sats: string[], t0: number, t1: number): number {
    let s = 0;
    const d0 = Math.round((t0 - this.start) / DAY);
    const d1 = Math.round((t1 - this.start) / DAY);
    for (const sat of sats) {
      const m = this.sats.get(sat);
      if (!m) continue;
      for (let d = d0; d <= d1; d++) s += m.get(d) ?? 0;
    }
    return s;
  }
}

export interface WindowRow {
  year: number;
  start: string;
  end: string;
  total: number;
  lower: number;
  upper: number;
  estimated: boolean;
}

export function windowTotals(
  series: MonthlySeries,
  daily: DailyIndex,
  startIso: string,
  endIso: string,
  lastDayIso: string,
): WindowRow[] {
  const start = parseDay(startIso);
  const end = parseDay(endIso);
  const lastDay = parseDay(lastDayIso);
  if (end < start) throw new Error("The end date is before the start date");
  if ((end - start) / DAY > 365) throw new Error("Choose at most one year");
  const byMonth = new Map(series.months.map((m, i) => [m, i]));
  const first = series.months[0];
  const rows: WindowRow[] = [];
  for (let k = -40; k <= 0; k++) {
    const s = addYears(start, k);
    const e = addYears(end, k);
    if (e > lastDay || isoDay(s).slice(0, 7) < first) continue;
    let tot = 0;
    let lo = 0;
    let hi = 0;
    let est = false;
    let ok = true;
    const sd = new Date(s);
    for (
      let y = sd.getUTCFullYear(), mo = sd.getUTCMonth();
      Date.UTC(y, mo, 1) <= e;
      mo === 11 ? ((y += 1), (mo = 0)) : (mo += 1)
    ) {
      const key = `${y}-${String(mo + 1).padStart(2, "0")}`;
      const i = byMonth.get(key);
      const v = i === undefined ? null : series.value[i];
      if (i === undefined || v === null) {
        ok = false;
        break;
      }
      const src = series.source[i];
      const sats = sources(src).filter((x) => daily.has(x));
      const m0 = Date.UTC(y, mo, 1);
      const m1 = Math.min(Date.UTC(y, mo + 1, 0), lastDay);
      const w0 = Math.max(s, m0);
      const w1 = Math.min(e, m1);
      const monthRaw = sats.length ? daily.sum(sats, m0, m1) : 0;
      const winRaw = sats.length ? daily.sum(sats, w0, w1) : 0;
      const share = monthRaw > 0 ? winRaw / monthRaw : ((w1 - w0) / DAY + 1) / ((m1 - m0) / DAY + 1);
      tot += v * share;
      lo += (series.lower[i] ?? v) * share;
      hi += (series.upper[i] ?? v) * share;
      est ||= series.estimated[i];
    }
    if (ok) {
      rows.push({ year: new Date(e).getUTCFullYear(), start: isoDay(s), end: isoDay(e), total: tot, lower: lo, upper: hi, estimated: est });
    }
  }
  return rows;
}

export interface WindowCompare {
  year: number;
  total: number;
  lower: number;
  upper: number;
  median: number;
  pctVsMedian: number | null;
  rank: number;
  nYears: number;
  firstYear: number;
  estimated: boolean;
}

/** burncal.daily.compare_window */
export function compareWindow(rows: WindowRow[], year: number): WindowCompare | null {
  const t = rows.find((r) => r.year === year);
  if (!t) return null;
  const others = rows.filter((r) => r.year !== year).map((r) => r.total);
  const med = median(others);
  return {
    year,
    total: t.total,
    lower: t.lower,
    upper: t.upper,
    median: med,
    pctVsMedian: med > 0 ? 100 * (t.total / med - 1) : null,
    rank: rows.filter((r) => r.total > t.total).length + 1,
    nYears: rows.length,
    firstYear: Math.min(...rows.map((r) => r.year)),
    estimated: t.estimated,
  };
}

/** app.py _pct_ok (MIN_MEDIAN_FOR_PCT = 20): a % change is shown only when the usual amount is large enough. */
export function pctOk(c: WindowCompare): boolean {
  return c.median >= 20 && c.pctVsMedian !== null;
}
