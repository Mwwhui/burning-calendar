import { describe, expect, it } from "vitest";

import type { PlaybackFrames } from "@/lib/data/types";

import { cellAreaKm2, cellPolygon, indexFrames, quantile } from "./frames";

const frames: PlaybackFrames = {
  step: "year", deg: 0.1, periods: ["2024", "2025"], totals: [3, 4], partial: "2025",
  p: [0, 0, 1], x: [1000, 1001, 1000], y: [20, 20, 21], v: [1, 2, 4],
};

describe("playback frames", () => {
  it("groups cells by period", () => {
    const f = indexFrames(frames);
    expect(Array.from(f.byPeriod[0])).toEqual([0, 1]);
    expect(Array.from(f.byPeriod[1])).toEqual([2]);
  });
  it("turns fire days into density per 1,000 km²", () => {
    const f = indexFrames(frames);
    const km2 = cellAreaKm2(0.1, 2.05);
    expect(f.density[1]).toBeCloseTo((1000 * 2) / km2, 4);
    expect(km2).toBeGreaterThan(123);
    expect(km2).toBeLessThan(124);
  });
  it("uses the detections' mean position when the export has one", () => {
    const f = indexFrames({ ...frames, x: undefined, y: undefined, lon: [100.013, 100.2, 100.05], lat: [2.017, 2.05, 2.11] });
    expect(f.lon[0]).toBeCloseTo(100.013);
    expect(f.lat[2]).toBeCloseTo(2.11);
    const poly = cellPolygon(f, 0);
    expect(poly[0][0]).toBeCloseTo(100.013 - 0.044);
  });
  it("draws coarse cells around their grid centre", () => {
    const poly = cellPolygon(indexFrames(frames), 0);
    for (const [lon, lat] of poly) {
      expect(lon).toBeGreaterThan(100);
      expect(lon).toBeLessThan(100.1);
      expect(lat).toBeGreaterThan(2);
      expect(lat).toBeLessThan(2.1);
    }
  });
  it("interpolates quantiles", () => {
    expect(quantile([0, 10], 0.5)).toBe(5);
    expect(quantile([], 0.5)).toBe(0);
  });
});
