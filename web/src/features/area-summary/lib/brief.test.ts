import { describe, expect, it } from "vitest";

import type { Summary } from "@/lib/data/types";

import { fireBrief } from "./brief";

const s: Summary = {
  peakMonth: 8, peakShare: 0.216, busiestYear: 2002, busiestYearTotal: 24485.3, busiestYearEstimated: true,
  busiestTies: [2014], partialMonth: "2026-11", thisYear: 2026, throughMonth: 10, thisYearToDate: 6027,
  rank: 20, nYears: 26, pctVsMedian: -49.2,
};

describe("fire brief", () => {
  it("states every number from the summary", () => {
    const text = fireBrief("Malaysia", s, "fire days", "El Niño").join(" ");
    expect(text).toContain("6,027 fire days in Jan–Oct 2026");
    expect(text).toContain("49 % below the median year");
    expect(text).toContain("20th highest of 26 years");
    expect(text).toContain("peaks in August");
    expect(text).toContain("22 %");
    expect(text).toContain("2002 (24,485 fire days, partly estimated");
    expect(text).toContain("2014 may have been as busy");
    expect(text).toContain("El Niño year");
  });
  it("describes ENSO for Argentina, not Southeast Asia", () => {
    const nino = fireBrief("Argentina", s, "fire days", "El Niño", false).join(" ");
    expect(nino).toContain("more rain to northeast Argentina");
    expect(nino).not.toContain("Southeast Asia");
    expect(fireBrief("Argentina", s, "fire days", "La Niña", false).join(" ")).toContain("drier seasons");
  });
  it("says 'close to' for small differences and skips missing ENSO", () => {
    const text = fireBrief("X", { ...s, pctVsMedian: 2, busiestTies: [] }, "fire days").join(" ");
    expect(text).toContain("close to the median year");
    expect(text).not.toContain("Niño");
    expect(text).not.toContain("may");
  });
});
