import { describe, expect, it } from "vitest";

import { buildSql, filesFor } from "./detections";

describe("hotspot search", () => {
  const index = { mys: { "2025": 10, "2026": 5 }, idn: { "2026": 7 } };

  it("reads only existing files for the years of the dates", () => {
    expect(filesFor(index, { countries: ["mys"], start: "2025-12-20", end: "2026-01-10" })).toEqual([
      "/detections/mys/2025.parquet",
      "/detections/mys/2026.parquet",
    ]);
    expect(filesFor(index, { countries: ["idn", "tha"], start: "2025-01-01", end: "2026-01-01" })).toEqual([
      "/detections/idn/2026.parquet",
    ]);
  });

  it("filters dates, regions, satellite and the drawn box, and escapes quotes", () => {
    const sql = buildSql(["https://x/a.parquet"], {
      countries: ["mys"],
      start: "2026-11-05",
      end: "2026-11-11",
      adm1: "Sarawak",
      adm2: "Ba'kelalan",
      satellite: "NOAA20",
      ring: [
        [110, 1],
        [112, 1],
        [112, 3],
        [110, 3],
      ],
    });
    expect(sql).toContain("solar_date BETWEEN DATE '2026-11-05' AND DATE '2026-11-11'");
    expect(sql).toContain("adm1 = 'Sarawak'");
    expect(sql).toContain("adm2 = 'Ba''kelalan'");
    expect(sql).toContain("satellite = 'NOAA20'");
    expect(sql).toContain("longitude BETWEEN 110 AND 112 AND latitude BETWEEN 1 AND 3");
    expect(sql).toContain("round(frp, 2) AS frp");
    expect(sql).toMatch(/LIMIT 500001$/);
  });
});
