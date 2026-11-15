import type { AreaExtraDetail, StepInfo } from "@/lib/data/types";

/** A seam test counts as unusual when its step is bigger than this share of ordinary year-to-year steps. */
export const UNUSUAL = 0.95;

/** Plain names of the satellite changes the pipeline tests (YYYY-MM of the switch). */
export function seamLabel(seam: string): string {
  if (seam.startsWith("2002")) return "Aqua joins Terra (2002)";
  if (seam.startsWith("2012")) return "MODIS → VIIRS (2012)";
  if (seam.startsWith("2018")) return "Suomi NPP → NOAA-20 (2018)";
  return seam;
}

export interface SeamRow {
  seam: string;
  label: string;
  stepPct: number | null;
  /** share of ordinary (placebo) steps smaller than this one, 0-1 */
  placebo: number | null;
  unusual: boolean;
}

export interface Consistency {
  seams: SeamRow[];
  nUnusual: number;
  /** step at the 2012 switch: naive record and harmonized, % */
  naive2012: number | null;
  harmonized2012: number | null;
}

export function consistency(extra: AreaExtraDetail): Consistency {
  const seams = extra.seams.rows.map((r) => ({
    seam: r.seam,
    label: seamLabel(r.seam),
    stepPct: r.stepPct,
    placebo: r.placebo,
    unusual: r.placebo !== null && r.placebo >= UNUSUAL,
  }));
  const s2012 = seams.find((r) => r.seam.startsWith("2012"));
  return {
    seams,
    nUnusual: seams.filter((r) => r.unusual).length,
    naive2012: extra.seams.naiveStep2012,
    harmonized2012: s2012?.stepPct ?? null,
  };
}

/**
 * The "do nothing" record per year, as in burncal.pipeline.naive_series: raw NOAA-20, else Suomi NPP,
 * else MODIS Terra + Aqua, month by month. Only the given (complete) years.
 */
export function naiveAnnual(raw: AreaExtraDetail["raw"], years: number[]): (number | null)[] {
  const get = (s: string, j: number) => raw.values[s]?.[j] ?? null;
  const tot = new Map<number, number>();
  raw.months.forEach((m, j) => {
    const viirs = get("NOAA20", j) ?? get("SNPP", j);
    const t = get("Terra", j);
    const a = get("Aqua", j);
    const v = viirs ?? (t === null && a === null ? null : (t ?? 0) + (a ?? 0));
    if (v === null) return;
    const y = Number(m.slice(0, 4));
    tot.set(y, (tot.get(y) ?? 0) + v);
  });
  return years.map((y) => tot.get(y) ?? null);
}

/** Signed percentage, e.g. "+199 %", "−6 %". */
export function signedPct(x: number | null | undefined): string {
  if (x === null || x === undefined) return "–";
  const r = Math.round(x);
  return `${r > 0 ? "+" : r < 0 ? "−" : "±"}${Math.abs(r)} %`;
}

/** Typical error of a conversion from its RMSE of log values, as ± percent. */
export function rmseToPct(rmse: number | null): number | null {
  return rmse === null ? null : (Math.exp(rmse) - 1) * 100;
}

const METHOD_NAME: Record<string, string> = {
  M0: "no conversion",
  M1: "one fixed ratio",
  M2: "a ratio per calendar month",
  M3: "log-linear fit",
  M4: "quantile mapping",
};

export function methodName(m: string | null): string {
  if (!m) return "–";
  return m
    .split("+")
    .map((x) => METHOD_NAME[x] ?? x)
    .join(" + ");
}

/** For each applied step: the method used and its error on hidden years, next to the best simpler rival. */
export function contest(steps: StepInfo[]) {
  return steps
    .filter((s) => s.status === "applied" && s.loyo && s.loyo.length)
    .map((s) => {
      const rows = [...s.loyo!].filter((r) => r.rmse !== null).sort((a, b) => a.rmse! - b.rmse!);
      // the row of the method used; a combined method (e.g. "M3+M2", two routes averaged) has no own row,
      // so the best single route stands for it
      const exact = rows.find((r) => r.method === s.method);
      const chosen = exact ?? rows[0];
      const runnerUp = rows.find((r) => r !== chosen && r.method !== chosen?.method);
      return {
        donor: s.donor,
        method: s.method,
        combined: !exact,
        chosenErr: rmseToPct(chosen?.rmse ?? null),
        runnerUp: runnerUp ? { method: runnerUp.method, err: rmseToPct(runnerUp.rmse) } : null,
        years: chosen?.years ?? null,
        drift: s.drift,
      };
    });
}

/** 0 and up to 4 round steps (1, 2, 2.5 or 5 x 10^n) covering `max`. */
export function niceTicks(max: number): number[] {
  if (!(max > 0)) return [0, 1];
  const raw = max / 4;
  const p = 10 ** Math.floor(Math.log10(raw));
  const step = [1, 2, 2.5, 5, 10].map((k) => k * p).find((k) => k >= raw)!;
  const out = [0];
  while (out[out.length - 1] < max) out.push(Number((out[out.length - 1] + step).toPrecision(12)));
  return out;
}
