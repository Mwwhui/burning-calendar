/**
 * Real satellite photos from NASA GIBS (Global Imagery Browse Services): free WMTS tiles, no key.
 * https://nasa-gibs.github.io/gibs-api-docs/
 *
 * Daily true colour (~250 m): NOAA-20 VIIRS from 2018, Suomi NPP VIIRS 2012-2018, Terra MODIS before.
 * 30 m true colour: HLS (Harmonized Landsat Sentinel-2), Landsat from 2013 and Sentinel-2 from late 2015,
 * a pass every few days; transparent where there is no image that day.
 */

const BASE = "https://gibs.earthdata.nasa.gov/wmts/epsg3857/best";

export interface ImageryLayer {
  id: string;
  name: string;
  tiles: string[];
  maxzoom: number;
  minzoom?: number;
}

function wmts(layer: string, date: string, tms: string, ext: string): string {
  return `${BASE}/${layer}/default/${date}/${tms}/{z}/{y}/{x}.${ext}`;
}

export type PhotoView = "true" | "swir";

/**
 * The daily ~250 m layer that best covers a date. "swir" = short-wave infrared false colour
 * (VIIRS M11-I2-I1, MODIS 7-2-1): sees through smoke (not cloud); burn scars red-brown, plants green.
 */
export function dailyLayer(date: string, view: PhotoView = "true"): ImageryLayer {
  const [sat, name] =
    date >= "2018-01-05"
      ? ["VIIRS_NOAA20", "NOAA-20 VIIRS"]
      : date >= "2012-01-20"
        ? ["VIIRS_SNPP", "Suomi NPP VIIRS"]
        : ["MODIS_Terra", "Terra MODIS"];
  const bands = view === "true" ? "TrueColor" : sat.startsWith("VIIRS") ? "BandsM11-I2-I1" : "Bands721";
  const id = `${sat}_CorrectedReflectance_${bands}`;
  return { id, name, tiles: [wmts(id, date, "GoogleMapsCompatible_Level9", "jpg")], maxzoom: 9 };
}

/** 30 m HLS layers available on a date (Sentinel-2 drawn above Landsat). */
export function detailLayers(date: string): ImageryLayer[] {
  const out: ImageryLayer[] = [];
  if (date >= "2013-04-01") {
    const id = "HLS_L30_Nadir_BRDF_Adjusted_Reflectance";
    out.push({ id, name: "Landsat 8/9 (HLS, 30 m)", tiles: [wmts(id, date, "GoogleMapsCompatible_Level12", "png")], maxzoom: 12, minzoom: 8 });
  }
  if (date >= "2015-11-28") {
    const id = "HLS_S30_Nadir_BRDF_Adjusted_Reflectance";
    out.push({ id, name: "Sentinel-2 (HLS, 30 m)", tiles: [wmts(id, date, "GoogleMapsCompatible_Level12", "png")], maxzoom: 12, minzoom: 8 });
  }
  return out;
}

export function shiftDay(iso: string, days: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
}

export const GIBS_CREDIT =
  "Imagery: NASA EOSDIS GIBS (VIIRS / MODIS Corrected Reflectance; HLS Landsat–Sentinel-2)";

/** Web-Mercator tile holding a point. */
export function tileXY(lon: number, lat: number, z: number): [number, number] {
  const n = 2 ** z;
  const x = Math.floor(((lon + 180) / 360) * n);
  const r = (lat * Math.PI) / 180;
  const y = Math.floor(((1 - Math.log(Math.tan(r) + 1 / Math.cos(r)) / Math.PI) / 2) * n);
  return [Math.min(n - 1, Math.max(0, x)), Math.min(n - 1, Math.max(0, y))];
}

/** A GIBS tile under this size is an empty (transparent) tile: no Landsat / Sentinel-2 pass that day. */
export const EMPTY_TILE_BYTES = 5000;

export interface DetailDay {
  date: string;
  /** "S" Sentinel-2, "L" Landsat */
  sat: "S" | "L";
  /** share of the picture (0-1) that looks like cloud or thick haze */
  cloud: number;
}

/**
 * Share of the opaque pixels (RGBA bytes) that look like cloud or thick haze: bright and nearly colourless
 * (mean of RGB > 120 and max - min < 40). Tuned by eye on Sarawak tiles: clear forest / plantation 0-2 %,
 * scattered cumulus 10-30 %, overcast 85-100 %. Bright bare soil or concrete can be counted as cloud.
 */
export function cloudShare(rgba: ArrayLike<number>): number {
  let n = 0;
  let c = 0;
  for (let i = 0; i + 3 < rgba.length; i += 4) {
    if (rgba[i + 3] === 0) continue;
    n++;
    const r = rgba[i];
    const g = rgba[i + 1];
    const b = rgba[i + 2];
    const mx = Math.max(r, g, b);
    const mn = Math.min(r, g, b);
    if ((r + g + b) / 3 > 120 && mx - mn < 40) c++;
  }
  return n ? c / n : 1;
}

/** cloud share of a tile, or null when there is no picture that day (empty tile) */
export type TileProbe = (url: string) => Promise<number | null>;

/**
 * Days with a 30 m picture over a point, with how cloudy each is: fetches the zoom-12 HLS tile of each day.
 * Cheap (an empty tile is ~300 bytes) and needs no key.
 */
export async function findDetailDays(
  lon: number,
  lat: number,
  days: string[],
  probe: TileProbe = probeTile,
  concurrency = 8,
): Promise<DetailDay[]> {
  const [x, y] = tileXY(lon, lat, 12);
  const jobs: { date: string; sat: "S" | "L"; url: string }[] = [];
  for (const date of days) {
    for (const l of detailLayers(date)) {
      const sat = l.id.startsWith("HLS_S30") ? "S" : "L";
      jobs.push({ date, sat, url: l.tiles[0].replace("{z}", "12").replace("{x}", String(x)).replace("{y}", String(y)) });
    }
  }
  const out: DetailDay[] = [];
  let next = 0;
  async function worker() {
    while (next < jobs.length) {
      const j = jobs[next++];
      const cloud = await probe(j.url).catch(() => null);
      if (cloud !== null) out.push({ date: j.date, sat: j.sat, cloud });
    }
  }
  await Promise.all(Array.from({ length: concurrency }, worker));
  return out.sort((a, b) => a.date.localeCompare(b.date) || a.sat.localeCompare(b.sat));
}

/** Browser probe: empty tile -> null, else the cloud share of a 64 x 64 copy of the tile. */
async function probeTile(url: string): Promise<number | null> {
  const r = await fetch(url);
  if (!r.ok) return null;
  const blob = await r.blob();
  if (blob.size < EMPTY_TILE_BYTES) return null;
  const bmp = await createImageBitmap(blob);
  const c = new OffscreenCanvas(64, 64);
  const ctx = c.getContext("2d");
  if (!ctx) return 0.5;
  ctx.drawImage(bmp, 0, 0, 64, 64);
  return cloudShare(ctx.getImageData(0, 0, 64, 64).data);
}

/** One entry per day: the clearer of Sentinel-2 and Landsat. */
export function clearestPerDay(found: DetailDay[]): DetailDay[] {
  const best = new Map<string, DetailDay>();
  for (const d of found) {
    const b = best.get(d.date);
    if (!b || d.cloud < b.cloud) best.set(d.date, d);
  }
  return [...best.values()].sort((a, b) => a.date.localeCompare(b.date));
}

/** A day counts as clear when at most this share of the picture is cloud. */
export const CLEAR_MAX = 0.25;

/** Days to search for 30 m pictures around a fire: three weeks before it started and after it ended. */
export function daysAround(start: string, end: string, latest: string, pad = 21): string[] {
  const out: string[] = [];
  const add = (a: string, b: string) => {
    for (let d = a; d <= b && d <= latest; d = shiftDay(d, 1)) if (!out.includes(d)) out.push(d);
  };
  add(shiftDay(start, -pad), shiftDay(start, 1));
  add(shiftDay(end, -1), shiftDay(end, pad));
  return out;
}

/**
 * Before / after pair from the 30 m days: the last clear day before the fire started and the first clear day
 * after it ended; if none is clear, the least cloudy day on that side.
 */
export function pickPair(found: DetailDay[], start: string, end: string): [DetailDay | null, DetailDay | null] {
  const days = clearestPerDay(found);
  const least = (xs: DetailDay[]) => xs.reduce<DetailDay | null>((m, d) => (m === null || d.cloud < m.cloud ? d : m), null);
  const before = days.filter((d) => d.date < start);
  const after = days.filter((d) => d.date > end);
  const b = [...before].reverse().find((d) => d.cloud <= CLEAR_MAX) ?? least([...before].reverse());
  const a = after.find((d) => d.cloud <= CLEAR_MAX) ?? least(after);
  return [b, a];
}

/**
 * OPERA DIST-ALERT (30 m, from 2023): vegetation cover lost, built from every clear Landsat / Sentinel-2 look,
 * so a single cloudy day hides little. Drawn through the "gibsdist" protocol, which makes "no disturbance" clear.
 */
export const DIST_FIRST = "2023-01-01";
export function distLayer(date: string): ImageryLayer | null {
  if (date < DIST_FIRST) return null;
  const id = "OPERA_L3_DIST-ALERT-HLS_Color_Index";
  return { id, name: "OPERA vegetation loss (30 m)", tiles: [wmts(id, date, "GoogleMapsCompatible_Level12", "png").replace("https://", "gibsdist://")], maxzoom: 12, minzoom: 8 };
}

/** OPERA DIST status colours (GIBS colormap OPERA_Vegetation_Disturbance_Status), simplified for the legend. */
export const DIST_LEGEND: { rgb: string; label: string }[] = [
  { rgb: "224,27,7", label: "lost ≥ 50 % of plant cover (confirmed)" },
  { rgb: "228,135,39", label: "≥ 50 % (provisional)" },
  { rgb: "222,224,67", label: "lost < 50 % (confirmed)" },
  { rgb: "0,136,136", label: "first seen, not yet confirmed" },
  { rgb: "119,119,119", label: "earlier loss, now ended" },
];

/** RGB of "no disturbance" and "no data" in DIST tiles: made transparent. */
export function isDistBackground(r: number, g: number, b: number): boolean {
  return (r === 18 && g === 18 && b === 18) || (r === 0 && g === 0 && b === 0);
}

/**
 * Haze and smoke, daily (NASA GIBS), drawn as a violet veil so it is not mistaken for fire:
 * - "aod": aerosol optical depth (how much the haze dims sunlight), VIIRS Deep Blue from the same satellite as the fire
 *   detections (NOAA-20 from 2018, Suomi NPP 2012-2018, Terra MODIS before). ~6-10 km; blank under cloud.
 * - "smoke": UV aerosol index (OMPS): smoke and dust that absorb UV, also seen above cloud; coarse (~17-50 km), from 2012.
 */
export type HazeKind = "aod" | "smoke";

export function hazeLayer(date: string, kind: HazeKind): ImageryLayer | null {
  let id: string;
  let name: string;
  if (kind === "aod") {
    if (date >= "2018-02-24") [id, name] = ["VIIRS_NOAA20_AOD_Deep_Blue_Land_Ocean", "NOAA-20 VIIRS"];
    else if (date >= "2012-03-01") [id, name] = ["VIIRS_SNPP_AOD_Deep_Blue_Land_Ocean", "Suomi NPP VIIRS"];
    else if (date >= "2000-02-24") [id, name] = ["MODIS_Terra_AOD_Deep_Blue_Combined", "Terra MODIS"];
    else return null;
  } else {
    if (date >= "2026-01-13") [id, name] = ["OMPS_NOAA20_NadirMapper_AerosolIndex_380", "NOAA-20 OMPS"];
    else if (date >= "2012-01-26") [id, name] = ["OMPS_Aerosol_Index", "Suomi NPP OMPS"];
    else return null;
  }
  const scheme = kind === "aod" ? "gibsaod://" : "gibsai://";
  return { id, name, tiles: [wmts(id, date, "GoogleMapsCompatible_Level6", "png").replace("https://", scheme)], maxzoom: 6 };
}

/** First day each haze view exists. */
export const HAZE_FIRST: Record<HazeKind, string> = { aod: "2000-02-24", smoke: "2012-01-26" };

/** Packed RGB -> value lookup of a GIBS colour table ([r, g, b, value, ...]). */
export function colormapLookup(flat: readonly number[]): Map<number, number> {
  const m = new Map<number, number>();
  for (let i = 0; i + 3 < flat.length; i += 4) m.set((flat[i] << 16) | (flat[i + 1] << 8) | flat[i + 2], flat[i + 3]);
  return m;
}

/** Where the veil starts (lighter is not drawn) and where it is darkest. */
export const HAZE_RANGE: Record<HazeKind, [number, number]> = { aod: [0.2, 2], smoke: [1, 4] };

// violet: stands out on light and dark basemaps and is never mistaken for fire (yellow-red)
const VEIL_LIGHT = [196, 181, 253];
const VEIL_DARK = [109, 40, 217];

/** Veil colour of a haze value: transparent below the start, then pale violet to strong violet, more opaque. */
export function hazeColor(v: number, kind: HazeKind): [number, number, number, number] {
  const [lo, hi] = HAZE_RANGE[kind];
  if (!(v >= lo)) return [0, 0, 0, 0];
  const t = Math.min(1, (v - lo) / (hi - lo));
  const c = VEIL_LIGHT.map((a, k) => Math.round(a + (VEIL_DARK[k] - a) * t));
  return [c[0], c[1], c[2], Math.round(90 + 100 * t)];
}

/** Recolour a GIBS haze tile in place (RGBA bytes); colours not in the table (no data, cloud) become transparent. */
export function recolorHaze(rgba: Uint8ClampedArray | number[], lookup: Map<number, number>, kind: HazeKind): void {
  for (let i = 0; i + 3 < rgba.length; i += 4) {
    const v = rgba[i + 3] === 0 ? undefined : lookup.get((rgba[i] << 16) | (rgba[i + 1] << 8) | rgba[i + 2]);
    const c = v === undefined ? [0, 0, 0, 0] : hazeColor(v, kind);
    rgba[i] = c[0];
    rgba[i + 1] = c[1];
    rgba[i + 2] = c[2];
    rgba[i + 3] = c[3];
  }
}

/** Legend steps of the haze veil. */
export const HAZE_LEGEND: Record<HazeKind, { v: number; label: string }[]> = {
  aod: [
    { v: 0.3, label: "light haze (0.2-0.5)" },
    { v: 0.7, label: "haze (0.5-1)" },
    { v: 1.5, label: "thick haze (1-2)" },
    { v: 2.5, label: "very thick smoke (2+)" },
  ],
  smoke: [
    { v: 1.5, label: "some smoke or dust (1-2)" },
    { v: 2.5, label: "smoke (2-3)" },
    { v: 3.5, label: "thick smoke (3+)" },
  ],
};
