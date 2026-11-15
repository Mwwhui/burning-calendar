import { describe, expect, it } from "vitest";

import type { AreaExtraDetail, StepInfo } from "@/lib/data/types";

import { consistency, contest, methodName, naiveAnnual, niceTicks, rmseToPct, seamLabel, signedPct } from "./consistency";

const seams: AreaExtraDetail["seams"] = {
  rows: [
    { seam: "2002-07", stepPct: 34, placebo: 0.91, nPlacebo: 11 },
    { seam: "2012-01", stepPct: 2.1, placebo: 0.27, nPlacebo: 11 },
    { seam: "2018-04", stepPct: 40, placebo: 0.97, nPlacebo: 11 },
  ],
  naiveStep2012: 199.2,
};

describe("consistency proof", () => {
  it("flags seams bigger than 95 % of ordinary steps and reads the 2012 steps", () => {
    const c = consistency({ seams } as AreaExtraDetail);
    expect(c.nUnusual).toBe(1);
    expect(c.seams[2].unusual).toBe(true);
    expect(c.naive2012).toBe(199.2);
    expect(c.harmonized2012).toBe(2.1);
    expect(seamLabel("2012-01")).toBe("MODIS → VIIRS (2012)");
  });

  it("builds the naive record like the pipeline: NOAA-20, else Suomi NPP, else Terra + Aqua", () => {
    const raw = {
      months: ["2011-12", "2012-01", "2018-05"],
      sats: ["Terra", "Aqua", "SNPP", "NOAA20"],
      values: { Terra: [1, 2, 3], Aqua: [10, 20, null], SNPP: [null, 100, 200], NOAA20: [null, null, 300] },
    };
    expect(naiveAnnual(raw, [2011, 2012, 2018, 2019])).toEqual([11, 100, 300, null]);
  });

  it("formats steps and errors", () => {
    expect(signedPct(199.2)).toBe("+199 %");
    expect(signedPct(-6.4)).toBe("−6 %");
    expect(signedPct(null)).toBe("–");
    expect(rmseToPct(0.075)).toBeCloseTo(7.79, 1);
    expect(methodName("M3+M2")).toBe("log-linear fit + a ratio per calendar month");
  });

  it("puts the method used next to the best other method", () => {
    const steps: StepInfo[] = [
      { donor: "SNPP", status: "applied", method: "M1", fitWindow: null, monthsFilled: 70, drift: -0.007, why: null,
        loyo: [{ method: "M0", route: null, rmse: 0.084, bias: -3.5, years: 8 }, { method: "M1", route: null, rmse: 0.075, bias: -0.1, years: 8 }] },
      { donor: "Aqua+Terra", status: "applied", method: "M3+M2", fitWindow: null, monthsFilled: 110, drift: null, why: null,
        loyo: [{ method: "M3", route: "Aqua", rmse: 0.133, bias: 0.1, years: 9 }, { method: "M2", route: "Aqua", rmse: 0.113, bias: -0.2, years: 9 }] },
      { donor: "Aqua", status: "skipped", method: null, fitWindow: null, monthsFilled: 0, drift: null, why: null, loyo: [] },
    ];
    const [a, b] = contest(steps);
    expect(contest(steps)).toHaveLength(2);
    expect(a.combined).toBe(false);
    expect(a.chosenErr).toBeCloseTo(7.79, 1);
    expect(a.runnerUp?.method).toBe("M0");
    expect(b.combined).toBe(true);
    expect(b.runnerUp?.method).toBe("M3");
  });
});

describe("chart ticks", () => {
  it("uses round steps", () => {
    expect(niceTicks(2_840_000)).toEqual([0, 1_000_000, 2_000_000, 3_000_000]);
    expect(niceTicks(170)).toEqual([0, 50, 100, 150, 200]);
    expect(niceTicks(0)).toEqual([0, 1]);
  });
});
