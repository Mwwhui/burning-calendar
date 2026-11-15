import { describe, expect, it } from "vitest";

import {
  clearestPerDay,
  cloudShare,
  dailyLayer,
  daysAround,
  detailLayers,
  distLayer,
  findDetailDays,
  isDistBackground,
  pickPair,
  shiftDay,
  tileXY,
  type DetailDay,
} from "./gibs";

describe("NASA GIBS imagery", () => {
  it("picks the daily satellite that flew on the date", () => {
    expect(dailyLayer("2026-09-10").id).toBe("VIIRS_NOAA20_CorrectedReflectance_TrueColor");
    expect(dailyLayer("2015-09-10").id).toBe("VIIRS_SNPP_CorrectedReflectance_TrueColor");
    expect(dailyLayer("2006-09-10").id).toBe("MODIS_Terra_CorrectedReflectance_TrueColor");
    expect(dailyLayer("2026-09-10").tiles[0]).toBe(
      "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/VIIRS_NOAA20_CorrectedReflectance_TrueColor/default/2026-09-10/GoogleMapsCompatible_Level9/{z}/{y}/{x}.jpg",
    );
  });
  it("adds 30 m Landsat and Sentinel-2 only when they existed", () => {
    expect(detailLayers("2010-01-01")).toEqual([]);
    expect(detailLayers("2014-06-01").map((l) => l.id)).toEqual(["HLS_L30_Nadir_BRDF_Adjusted_Reflectance"]);
    expect(detailLayers("2026-09-10")).toHaveLength(2);
  });
  it("steps days across month ends", () => {
    expect(shiftDay("2026-03-01", -1)).toBe("2026-02-28");
    expect(shiftDay("2024-02-28", 1)).toBe("2024-02-29");
  });
});

describe("finding 30 m pictures", () => {
  it("computes the tile under a point", () => {
    expect(tileXY(113.4, 3.1, 12)).toEqual([3338, 2012]);
    expect(tileXY(0, 0, 1)).toEqual([1, 1]);
  });
  it("scores cloud as bright colourless pixels, ignoring transparent ones", () => {
    const px = (r: number, g: number, b: number, a = 255) => [r, g, b, a];
    const forest = px(40, 90, 40);
    const cloud = px(230, 232, 235);
    const haze = px(170, 175, 168);
    const soil = px(170, 130, 90); // bright but coloured: not cloud
    expect(cloudShare([...forest, ...forest, ...cloud, ...soil])).toBe(0.25);
    expect(cloudShare([...haze, ...cloud, ...px(0, 0, 0, 0)])).toBe(1);
    expect(cloudShare([])).toBe(1);
  });
  it("keeps only days with a picture, Sentinel-2 and Landsat separately", async () => {
    const cloud: Record<string, number> = { "2026-07-31": 0.01, "2026-08-02": 0.86 };
    const probe = async (url: string) => {
      const d = url.match(/default\/(\d{4}-\d{2}-\d{2})/)![1];
      if (url.includes("HLS_S30")) return cloud[d] ?? null;
      return d === "2026-07-31" ? 0.02 : null;
    };
    const got = await findDetailDays(113.4, 3.1, ["2026-07-30", "2026-07-31", "2026-08-01", "2026-08-02"], probe);
    expect(got).toEqual([
      { date: "2026-07-31", sat: "L", cloud: 0.02 },
      { date: "2026-07-31", sat: "S", cloud: 0.01 },
      { date: "2026-08-02", sat: "S", cloud: 0.86 },
    ]);
    expect(clearestPerDay(got).map((d) => [d.date, d.sat])).toEqual([["2026-07-31", "S"], ["2026-08-02", "S"]]);
  });
  it("searches around the start and end of the fire", () => {
    const days = daysAround("2026-08-01", "2026-08-22", "2026-08-30", 3);
    expect(days[0]).toBe("2026-07-29");
    expect(days.at(-1)).toBe("2026-08-25");
    expect(days).not.toContain("2026-08-10");
    expect(daysAround("2026-11-10", "2026-11-12", "2026-11-13", 3).at(-1)).toBe("2026-11-13");
  });
  it("picks the nearest clear day on each side, else the least cloudy", () => {
    const d = (date: string, cloud: number): DetailDay => ({ date, sat: "S", cloud });
    // Sebauh, Sarawak, 1-22 Aug 2026 (cloud shares measured on the real tiles)
    const found = [d("2026-07-21", 0.02), d("2026-07-31", 0.02), d("2026-08-24", 0.3), d("2026-08-30", 1), d("2026-09-11", 0.13)];
    const [b, a] = pickPair(found, "2026-08-01", "2026-08-22");
    expect(b?.date).toBe("2026-07-31");
    expect(a?.date).toBe("2026-09-11"); // 24 Aug is hazy, 11 Sep is the first clear day
    const [b2, a2] = pickPair([d("2026-07-20", 0.9), d("2026-07-30", 0.6), d("2026-08-25", 0.7), d("2026-08-28", 0.4)], "2026-08-01", "2026-08-22");
    expect(b2?.date).toBe("2026-07-30");
    expect(a2?.date).toBe("2026-08-28");
    expect(pickPair([], "2026-08-01", "2026-08-22")).toEqual([null, null]);
  });
});

describe("cloud-proof views", () => {
  it("switches the daily layer to short-wave infrared", () => {
    expect(dailyLayer("2026-09-10", "swir").id).toBe("VIIRS_NOAA20_CorrectedReflectance_BandsM11-I2-I1");
    expect(dailyLayer("2006-09-10", "swir").id).toBe("MODIS_Terra_CorrectedReflectance_Bands721");
  });
  it("offers vegetation loss from 2023 through the transparent-background protocol", () => {
    expect(distLayer("2022-12-31")).toBeNull();
    expect(distLayer("2026-09-11")!.tiles[0]).toMatch(/^gibsdist:\/\/gibs\.earthdata\.nasa\.gov\/.*OPERA_L3_DIST-ALERT-HLS_Color_Index\/default\/2026-09-11\//);
    expect(isDistBackground(18, 18, 18)).toBe(true);
    expect(isDistBackground(224, 27, 7)).toBe(false);
  });
});

import { AI_COLORMAP, AOD_COLORMAP } from "./haze-colormaps";
import { colormapLookup, hazeColor, hazeLayer, recolorHaze } from "./gibs";

describe("haze layer", () => {
  it("uses the satellite that flew on the date", () => {
    expect(hazeLayer("2026-09-10", "aod")!.id).toBe("VIIRS_NOAA20_AOD_Deep_Blue_Land_Ocean");
    expect(hazeLayer("2015-09-10", "aod")!.id).toBe("VIIRS_SNPP_AOD_Deep_Blue_Land_Ocean");
    expect(hazeLayer("2006-09-10", "aod")!.id).toBe("MODIS_Terra_AOD_Deep_Blue_Combined");
    expect(hazeLayer("2026-09-10", "smoke")!.id).toBe("OMPS_NOAA20_NadirMapper_AerosolIndex_380");
    expect(hazeLayer("2019-09-10", "smoke")!.id).toBe("OMPS_Aerosol_Index");
    expect(hazeLayer("2006-09-10", "smoke")).toBeNull();
    expect(hazeLayer("2026-09-10", "aod")!.tiles[0]).toMatch(/^gibsaod:\/\/gibs\.earthdata\.nasa\.gov\/.*\/2026-09-10\/GoogleMapsCompatible_Level6\/\{z\}\/\{y\}\/\{x\}\.png$/);
  });

  it("reads values back from the GIBS colours and draws a veil only where it is hazy", () => {
    const aod = colormapLookup(AOD_COLORMAP);
    expect(aod.size).toBe(AOD_COLORMAP.length / 4);
    expect(aod.get((255 << 16) | (252 << 8) | 199)).toBeCloseTo(0.0025, 6);
    expect(colormapLookup(AI_COLORMAP).get((115 << 16) | 25)).toBe(5);
    expect(hazeColor(0.1, "aod")[3]).toBe(0);
    expect(hazeColor(2.5, "aod")[3]).toBeGreaterThan(hazeColor(0.5, "aod")[3]);
    const px = [255, 252, 199, 255, 125, 0, 14, 255, 1, 2, 3, 255];
    recolorHaze(px, aod, "aod");
    expect(px[3]).toBe(0); // clean air
    expect(px[7]).toBe(190); // thickest: see-through, it lies over the fire
    expect(px[11]).toBe(0); // colour not in the table
  });
});
