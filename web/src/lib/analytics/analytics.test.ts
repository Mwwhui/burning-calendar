import { describe, expect, it } from "vitest";

import type { AnnualSeries, CellsData, MonthlySeries } from "@/lib/data/types";

import { ownAreaSeries, pointInRing, ringKm2 } from "./own-area";
import { anomalyZ, cumulativeByYear, median, summaryFor, toGrid } from "./series";
import { compareWindow, DailyIndex, sources, windowTotals } from "./window";

function monthly(from: number, to: number, f: (y: number, m: number) => number, est = (y: number) => y < 2018): MonthlySeries {
  const s: MonthlySeries = { months: [], value: [], lower: [], upper: [], estimated: [], source: [] };
  for (let y = from; y <= to; y++)
    for (let m = 1; m <= 12; m++) {
      const v = f(y, m);
      s.months.push(`${y}-${String(m).padStart(2, "0")}`);
      s.value.push(v);
      s.lower.push(est(y) ? v * 0.8 : v);
      s.upper.push(est(y) ? v * 1.25 : v);
      s.estimated.push(est(y));
      s.source.push(est(y) ? "SNPP converted" : "NOAA20 measured");
    }
  return s;
}

describe("series maths", () => {
  it("builds a year grid and running totals", () => {
    const g = toGrid(["2020-01", "2020-03"], [5, 7]);
    expect(g.get(2020)).toEqual([5, null, 7, null, null, null, null, null, null, null, null, null]);
    expect(cumulativeByYear(g).get(2020)!.slice(0, 3)).toEqual([5, null, 12]);
    expect(median([3, 1, 2, 10])).toBe(2.5);
  });
  it("scores unusual months against the baseline", () => {
    const s = monthly(2003, 2006, (y, m) => (m === 1 ? 10 * y - 20020 : 10));
    const z = anomalyZ(toGrid(s.months, s.value), [2003, 2006]);
    expect(z.get(2006)![0]!).toBeGreaterThan(0.8);
    expect(z.get(2003)![0]!).toBeLessThan(-0.8);
    expect(z.get(2004)![5]).toBeNull(); // no spread in June
  });
  it("summarises like app/data.py summary_numbers", () => {
    const s = monthly(2016, 2020, (y, m) => (y === 2019 ? 2 : 1) * (m === 8 ? 50 : 10));
    s.months.push("2021-01", "2021-02");
    s.value.push(30, 5);
    s.lower.push(30, 5);
    s.upper.push(30, 5);
    s.estimated.push(false, false);
    s.source.push("NOAA20 measured", "NOAA20 measured");
    const sum = summaryFor(s, "2021-02")!;
    expect(sum.peakMonth).toBe(8);
    expect(sum.busiestYear).toBe(2019);
    expect(sum.thisYear).toBe(2021);
    expect(sum.throughMonth).toBe(1);
    expect(sum.thisYearToDate).toBe(30);
    expect(sum.rank).toBe(1);
    expect(sum.nYears).toBe(6);
    expect(sum.pctVsMedian).toBeCloseTo(200, 6);
  });
});

describe("date windows", () => {
  it("splits each month by the source satellite's daily share", () => {
    // NOAA20 fire only on the 1st of every month: a window of the 1st holds the whole month
    const s = monthly(2019, 2020, () => 100, () => false);
    const d: number[] = [];
    const v: number[] = [];
    const t0 = Date.UTC(2019, 0, 1);
    for (let y = 2019; y <= 2020; y++)
      for (let m = 0; m < 12; m++) {
        d.push(Math.round((Date.UTC(y, m, 1) - t0) / 86_400_000));
        v.push(4);
      }
    const daily = new DailyIndex({ start: "2019-01-01", sats: { NOAA20: { d, v } } });
    const rows = windowTotals(s, daily, "2020-03-01", "2020-03-02", "2020-12-31");
    expect(rows.map((r) => r.year)).toEqual([2019, 2020]);
    expect(rows[1].total).toBeCloseTo(100);
    const half = windowTotals(s, daily, "2020-03-02", "2020-03-31", "2020-12-31");
    expect(half[1].total).toBeCloseTo(0);
    const c = compareWindow(rows, 2020)!;
    expect(c.rank).toBe(1);
    expect(c.nYears).toBe(2);
  });
  it("rejects bad ranges and reads source labels", () => {
    const s = monthly(2020, 2020, () => 1);
    const daily = new DailyIndex({ start: "2020-01-01", sats: {} });
    expect(() => windowTotals(s, daily, "2020-05-01", "2020-04-01", "2020-12-31")).toThrow();
    expect(sources("Aqua+Terra converted (M3)")).toEqual(["Aqua", "Terra"]);
  });
});

describe("own areas", () => {
  const square: [number, number][] = [
    [100, 2],
    [100.3, 2],
    [100.3, 2.3],
    [100, 2.3],
  ];
  it("tests points and areas", () => {
    expect(pointInRing(100.15, 2.15, square)).toBe(true);
    expect(pointInRing(100.35, 2.15, square)).toBe(false);
    expect(ringKm2(square)).toBeGreaterThan(1100);
    expect(ringKm2(square)).toBeLessThan(1120);
  });
  it("sums the cells inside and scales the likely range", () => {
    const country = monthly(2017, 2018, () => 100);
    const annual: AnnualSeries = { years: [2017, 2018], total: [1200, 1200], lower: [960, 1200], upper: [1500, 1200], estimatedShare: [1, 0] };
    const cells: CellsData = {
      deg: 0.1,
      months: ["2017-01", "2018-01"],
      m: [0, 0, 1],
      x: [1000, 1010, 1000],
      y: [20, 20, 21],
      v: [30, 70, 40],
    };
    const r = ownAreaSeries(cells, square, country, annual);
    expect(r.nCells).toBe(2);
    expect(r.series.value[0]).toBeCloseTo(30);
    expect(r.series.lower[0]).toBeCloseTo(24);
    expect(r.series.value[12]).toBeCloseTo(40);
    expect(r.annual.years).toEqual([2017, 2018]);
    expect(r.annual.lower[0]).toBeCloseTo(24);
  });
});

import { boxRing, circleRing } from "./shapes";

describe("coordinate shapes", () => {
  it("builds a circle of the right size", () => {
    const r = circleRing(3, 101.5, 25);
    expect(ringKm2(r)).toBeGreaterThan(1940); // pi * 25^2 = 1963
    expect(ringKm2(r)).toBeLessThan(1970);
    expect(pointInRing(101.5, 3, r)).toBe(true);
  });
  it("rejects an upside-down box", () => {
    expect(() => boxRing(102, 3, 101, 4)).toThrow();
    expect(boxRing(101, 2, 102, 3)).toHaveLength(4);
  });
});
