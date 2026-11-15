import { interpolateYlOrRd } from "d3-scale-chromatic";

import type { EventDots } from "@/lib/data/types";
import type { RGBA } from "@/lib/colors";
import { shiftDay } from "@/lib/gibs";

/** An event's cell-days ready for the map. */
export interface Dots {
  n: number;
  lon: Float64Array;
  lat: Float64Array;
  day: Int32Array;
  frp: Int32Array;
  /** half of a cell side, degrees */
  half: number;
  /** last day offset (days the fire lasted - 1) */
  last: number;
  start: string;
  /** squares burning on each day offset */
  perDay: number[];
}

export function decodeDots(e: EventDots): Dots {
  const n = e.d.length;
  const lon = new Float64Array(n);
  const lat = new Float64Array(n);
  for (let i = 0; i < n; i++) {
    lon[i] = (e.gx0 + e.gx[i] + 0.5) * e.grid;
    lat[i] = (e.gy0 + e.gy[i] + 0.5) * e.grid;
  }
  const last = n ? e.d[n - 1] : 0;
  const perDay = new Array<number>(last + 1).fill(0);
  for (const d of e.d) perDay[d]++;
  return { n, lon, lat, day: Int32Array.from(e.d), frp: Int32Array.from(e.frp), half: e.grid / 2, last, start: e.start, perDay };
}

/** Squares seen burning up to and including day `upTo` (all when null). */
export function seenBy(dots: Dots, upTo: number | null): number {
  if (upTo === null) return dots.n;
  let c = 0;
  for (let d = 0; d <= Math.min(upTo, dots.last); d++) c += dots.perDay[d];
  return c;
}

/** Colour of a cell by when it burned in the fire: first days pale yellow, last days dark red. */
export function dayColor(day: number, last: number, alpha = 235): RGBA {
  const t = last > 0 ? day / last : 1;
  const m = interpolateYlOrRd(0.2 + 0.8 * t).match(/\d+/g)!.map(Number);
  return [m[0], m[1], m[2], alpha];
}

export function dotDate(dots: Dots, day: number): string {
  return shiftDay(dots.start, day);
}
