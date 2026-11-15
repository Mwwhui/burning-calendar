import { describe, expect, it } from "vitest";

import { dayColor, decodeDots, dotDate, seenBy } from "./dots";

const raw = { id: 1, start: "2026-08-06", grid: 0.01, gx0: 11179, gy0: -349, gx: [0, 1, 1, 3], gy: [0, 0, 1, 2], d: [0, 0, 2, 5], frp: [10, 3, 40, 7] };

describe("event dots", () => {
  it("decodes cell centres and days", () => {
    const d = decodeDots(raw);
    expect(d.n).toBe(4);
    expect(d.lon[0]).toBeCloseTo(111.795, 9);
    expect(d.lat[3]).toBeCloseTo(-3.465, 9);
    expect(d.last).toBe(5);
    expect(d.perDay).toEqual([2, 0, 1, 0, 0, 1]);
    expect(dotDate(d, 5)).toBe("2026-08-11");
  });

  it("counts squares seen so far", () => {
    const d = decodeDots(raw);
    expect(seenBy(d, null)).toBe(4);
    expect(seenBy(d, 0)).toBe(2);
    expect(seenBy(d, 3)).toBe(3);
    expect(seenBy(d, 99)).toBe(4);
  });

  it("colours early days pale and late days dark", () => {
    const early = dayColor(0, 10);
    const late = dayColor(10, 10);
    expect(early[0] + early[1] + early[2]).toBeGreaterThan(late[0] + late[1] + late[2]);
    expect(dayColor(0, 0)).toEqual(late);
  });
});
