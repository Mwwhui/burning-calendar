import { interpolateRdBu, interpolateYlOrRd } from "d3-scale-chromatic";

export type RGBA = [number, number, number, number];

function parseRgb(css: string): [number, number, number] {
  const m = css.match(/\d+(\.\d+)?/g);
  if (!m || m.length < 3) return [128, 128, 128];
  return [Number(m[0]), Number(m[1]), Number(m[2])];
}

/** Sequential fire colour for t in [0, 1] (YlOrRd, colourblind-safe). */
export function fireColor(t: number, alpha = 255): RGBA {
  const c = parseRgb(interpolateYlOrRd(0.08 + 0.92 * clamp01(t)));
  return [c[0], c[1], c[2], alpha];
}

export function fireCss(t: number): string {
  return interpolateYlOrRd(0.08 + 0.92 * clamp01(t));
}

/**
 * Diverging change colour (RdBu reversed: blue = less fire, red = more),
 * clipped at ±`limit` %.
 */
export function changeColor(pct: number, limit = 100, alpha = 255): RGBA {
  const t = 0.5 - Math.max(-1, Math.min(1, pct / limit)) / 2;
  const c = parseRgb(interpolateRdBu(t));
  return [c[0], c[1], c[2], alpha];
}

export function changeCss(pct: number, limit = 100): string {
  const t = 0.5 - Math.max(-1, Math.min(1, pct / limit)) / 2;
  return interpolateRdBu(t);
}

export function clamp01(x: number): number {
  return Number.isFinite(x) ? Math.max(0, Math.min(1, x)) : 0;
}

/** Position of a count on a log colour scale with the given maximum. */
export function logScale(value: number, max: number): number {
  if (!(value > 0) || !(max > 0)) return 0;
  return clamp01(Math.log10(value + 1) / Math.log10(max + 1));
}
