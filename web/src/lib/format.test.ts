import { describe, expect, it } from "vitest";

import { formatCompact, formatDay, formatInt, formatPct, formatPeriod, monthSpan, ordinal } from "./format";

describe("format", () => {
  it("formats integers and gaps", () => {
    expect(formatInt(12345.4)).toBe("12,345");
    expect(formatInt(null)).toBe("–");
    expect(formatInt(Number.NaN)).toBe("–");
  });
  it("compacts numbers for small cells", () => {
    expect(formatCompact(950)).toBe("950");
    expect(formatCompact(1300)).toBe("1.3k");
    expect(formatCompact(2000)).toBe("2k");
    expect(formatCompact(12_400)).toBe("12k");
    expect(formatCompact(1_250_000)).toBe("1.3M");
    expect(formatCompact(null)).toBe("");
  });
  it("signs percentages with a true minus", () => {
    expect(formatPct(23.9)).toBe("+24 %");
    expect(formatPct(-17.1)).toBe("−17 %");
    expect(formatPct(0.2)).toBe("0 %");
  });
  it("writes ordinals", () => {
    expect([1, 2, 3, 4, 11, 12, 13, 21, 22, 101].map(ordinal)).toEqual([
      "1st", "2nd", "3rd", "4th", "11th", "12th", "13th", "21st", "22nd", "101st",
    ]);
  });
  it("formats periods and spans", () => {
    expect(formatPeriod("2026-03")).toBe("Mar 2026");
    expect(formatPeriod("2015")).toBe("2015");
    expect(monthSpan(10)).toBe("Jan–Oct");
    expect(monthSpan(1)).toBe("Jan");
    expect(formatDay("2026-11-11")).toBe("11 Nov 2026");
  });
});
