import type { PlaybackFrames } from "@/lib/data/types";

export interface IndexedFrames {
  data: PlaybackFrames;
  /** dot indices of each period */
  byPeriod: Uint32Array[];
  /** dot positions [lon, lat] */
  lon: Float64Array;
  lat: Float64Array;
  /** fire days per 1,000 km² of each dot's cell */
  density: Float32Array;
  /** 99.5th percentile of density over all periods (colour/height scale maximum) */
  maxDensity: number;
}

const KM_PER_DEG = 111.32;

export function cellAreaKm2(deg: number, latDeg: number): number {
  return (KM_PER_DEG * deg) ** 2 * Math.cos((latDeg * Math.PI) / 180);
}

export function quantile(values: Float32Array | number[], q: number): number {
  if (values.length === 0) return 0;
  const s = Float64Array.from(values).sort();
  const pos = (s.length - 1) * q;
  const lo = Math.floor(pos);
  const hi = Math.ceil(pos);
  return s[lo] + (s[hi] - s[lo]) * (pos - lo);
}

/**
 * Group dots by period, work out positions and densities once per file.
 * Fine exports give each dot the mean position of its detections; older coarse
 * exports only give a grid cell, drawn at its centre.
 */
export function indexFrames(data: PlaybackFrames): IndexedFrames {
  const n = data.v.length;
  const counts = new Uint32Array(data.periods.length);
  for (let i = 0; i < n; i++) counts[data.p[i]]++;
  const byPeriod = Array.from(counts, (c) => new Uint32Array(c));
  const fill = new Uint32Array(data.periods.length);
  const lon = new Float64Array(n);
  const lat = new Float64Array(n);
  const density = new Float32Array(n);
  for (let i = 0; i < n; i++) {
    const p = data.p[i];
    byPeriod[p][fill[p]++] = i;
    if (data.lon && data.lat) {
      lon[i] = data.lon[i];
      lat[i] = data.lat[i];
    } else {
      lon[i] = (data.x![i] + 0.5) * data.deg;
      lat[i] = (data.y![i] + 0.5) * data.deg;
    }
    density[i] = (1000 * data.v[i]) / cellAreaKm2(data.deg, lat[i]);
  }
  return { data, byPeriod, lon, lat, density, maxDensity: Math.max(quantile(density, 0.995), 1) };
}

/** Square of one display cell centred on the dot, [lon, lat] corners (3D columns). */
export function cellPolygon(f: IndexedFrames, i: number): [number, number][] {
  const h = (f.data.deg * 0.88) / 2;
  const x = f.lon[i];
  const y = f.lat[i];
  return [
    [x - h, y - h],
    [x + h, y - h],
    [x + h, y + h],
    [x - h, y + h],
  ];
}
