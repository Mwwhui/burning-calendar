/**
 * Own areas (drawn shapes). The country's harmonized monthly fire days are exported per
 * 0.1° cell, already split in proportion to each month's raw detections from the satellite(s)
 * that month comes from (burncal.playback.cell_frames). An own area's record is the sum of the
 * cells whose centre lies inside the shape; its likely range scales with the country's.
 *
 * Difference from the Streamlit app: there the drawn area was converted again on its own
 * detections (app/data.py compute_custom). Here it reuses the country's conversion, which is
 * the same like-for-like split the playback map uses. Totals agree for areas with many fires;
 * for small areas the Streamlit version could stop at "too few fires" instead.
 */
import type { AnnualSeries, BBox, CellsData, MonthlySeries } from "@/lib/data/types";

export type Ring = [number, number][];

/** Ray casting point-in-polygon (lon/lat ring, closed or open). */
export function pointInRing(lon: number, lat: number, ring: Ring): boolean {
  let inside = false;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    const [xi, yi] = ring[i];
    const [xj, yj] = ring[j];
    if (yi > lat !== yj > lat && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) inside = !inside;
  }
  return inside;
}

export function ringBBox(ring: Ring): BBox {
  const xs = ring.map((p) => p[0]);
  const ys = ring.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}

/** Approximate area of a lon/lat ring in km² (shoelace on an equirectangular projection). */
export function ringKm2(ring: Ring): number {
  const lat0 = (ringBBox(ring)[1] + ringBBox(ring)[3]) / 2;
  const kx = 111.32 * Math.cos((lat0 * Math.PI) / 180);
  let a = 0;
  for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
    a += ring[j][0] * kx * ring[i][1] * 111.32 - ring[i][0] * kx * ring[j][1] * 111.32;
  }
  return Math.abs(a) / 2;
}

export interface OwnAreaResult {
  series: MonthlySeries;
  annual: AnnualSeries;
  nCells: number;
}

/**
 * Monthly record of the cells inside `ring`, on the country's months. `country` gives each
 * month's likely range (as a ratio to its value) and source.
 */
export function ownAreaSeries(cells: CellsData, ring: Ring, country: MonthlySeries, countryAnnual: AnnualSeries): OwnAreaResult {
  const d = cells.deg;
  const [w, s, e, n] = ringBBox(ring);
  const sums = new Float64Array(cells.months.length);
  const inside = new Set<number>();
  for (let i = 0; i < cells.v.length; i++) {
    const lon = (cells.x[i] + 0.5) * d;
    const lat = (cells.y[i] + 0.5) * d;
    if (lon < w || lon > e || lat < s || lat > n) continue;
    if (!pointInRing(lon, lat, ring)) continue;
    sums[cells.m[i]] += cells.v[i];
    inside.add(cells.x[i] * 100_000 + cells.y[i]);
  }
  const cm = new Map(cells.months.map((m, i) => [m, i]));
  const series: MonthlySeries = { months: [], value: [], lower: [], upper: [], estimated: [], source: [] };
  country.months.forEach((m, i) => {
    const cv = country.value[i];
    if (cv === null) return;
    const ci = cm.get(m);
    const v = ci === undefined ? 0 : sums[ci];
    const lo = country.lower[i];
    const hi = country.upper[i];
    series.months.push(m);
    series.value.push(v);
    series.lower.push(cv > 0 && lo !== null ? (v * lo) / cv : v);
    series.upper.push(cv > 0 && hi !== null ? (v * hi) / cv : v);
    series.estimated.push(country.estimated[i]);
    series.source.push(country.source[i]);
  });
  // yearly totals over complete years, with the country's relative yearly range
  const byYear = new Map<number, { t: number; n: number }>();
  series.months.forEach((m, i) => {
    const y = Number(m.slice(0, 4));
    const r = byYear.get(y) ?? { t: 0, n: 0 };
    r.t += series.value[i] ?? 0;
    r.n += 1;
    byYear.set(y, r);
  });
  const annual: AnnualSeries = { years: [], total: [], lower: [], upper: [], estimatedShare: [] };
  countryAnnual.years.forEach((y, i) => {
    const r = byYear.get(y);
    const ct = countryAnnual.total[i];
    if (!r || r.n < 12 || ct === null) return;
    annual.years.push(y);
    annual.total.push(r.t);
    annual.lower.push(ct > 0 && countryAnnual.lower[i] !== null ? (r.t * countryAnnual.lower[i]!) / ct : r.t);
    annual.upper.push(ct > 0 && countryAnnual.upper[i] !== null ? (r.t * countryAnnual.upper[i]!) / ct : r.t);
    annual.estimatedShare.push(countryAnnual.estimatedShare[i]);
  });
  return { series, annual, nCells: inside.size };
}
