"use client";

/**
 * Hotspot (fire detection) search in the browser: DuckDB-wasm reads the per-country, per-year
 * Parquet files written by `scripts/export_points.py` (web/public/detections/) over HTTP range
 * requests, so only the row groups of the chosen dates are downloaded.
 */
import type { AsyncDuckDB } from "@duckdb/duckdb-wasm";

import { pointInRing, ringBBox, type Ring } from "@/lib/analytics/own-area";

export const DETECTIONS_BASE = "/detections";
export const MAX_ROWS = 500_000;

export const DETECTION_COLUMNS = [
  "latitude",
  "longitude",
  "acq_date",
  "acq_time",
  "solar_date",
  "satellite",
  "confidence",
  "frp",
  "daynight",
  "adm1",
  "adm2",
] as const;

export type DetectionRow = Record<(typeof DETECTION_COLUMNS)[number], string | number | null>;

let dbPromise: Promise<AsyncDuckDB> | null = null;

/** One DuckDB-wasm instance per page, created on first use (the engine is ~7 MB). */
export function getDb(): Promise<AsyncDuckDB> {
  if (!dbPromise) {
    dbPromise = (async () => {
      const duckdb = await import("@duckdb/duckdb-wasm");
      const base = `${window.location.origin}/vendor/duckdb`;
      const bundle = await duckdb.selectBundle({
        mvp: { mainModule: `${base}/duckdb-mvp.wasm`, mainWorker: `${base}/duckdb-browser-mvp.worker.js` },
        eh: { mainModule: `${base}/duckdb-eh.wasm`, mainWorker: `${base}/duckdb-browser-eh.worker.js` },
      });
      const worker = new Worker(bundle.mainWorker!);
      const db = new duckdb.AsyncDuckDB(new duckdb.VoidLogger(), worker);
      await db.instantiate(bundle.mainModule, bundle.pthreadWorker);
      return db;
    })();
    dbPromise.catch(() => (dbPromise = null));
  }
  return dbPromise;
}

/** country (lower-case ISO3) -> year -> rows */
export type DetectionsIndex = Record<string, Record<string, number>>;

export interface DetectionQuery {
  countries: string[];
  start: string; // ISO day (local solar date)
  end: string;
  adm1?: string | null;
  adm2?: string | null;
  satellite?: string | null;
  /** own area: keep detections inside this ring */
  ring?: Ring | null;
}

const q = (s: string) => `'${s.replace(/'/g, "''")}'`;

/** Files to read for a query (only those that exist). */
export function filesFor(index: DetectionsIndex, query: DetectionQuery): string[] {
  const y0 = Number(query.start.slice(0, 4));
  const y1 = Number(query.end.slice(0, 4));
  const out: string[] = [];
  for (const c of query.countries) {
    for (let y = y0; y <= y1; y++) if (index[c]?.[String(y)]) out.push(`${DETECTIONS_BASE}/${c}/${y}.parquet`);
  }
  return out;
}

/** The SQL for a query (exported for tests). */
export function buildSql(urls: string[], query: DetectionQuery): string {
  const where = [`solar_date BETWEEN DATE ${q(query.start)} AND DATE ${q(query.end)}`];
  if (query.adm1) where.push(`adm1 = ${q(query.adm1)}`);
  if (query.adm2) where.push(`adm2 = ${q(query.adm2)}`);
  if (query.satellite) where.push(`satellite = ${q(query.satellite)}`);
  if (query.ring) {
    const [w, s, e, n] = ringBBox(query.ring);
    where.push(`longitude BETWEEN ${w} AND ${e} AND latitude BETWEEN ${s} AND ${n}`);
  }
  return (
    `SELECT ${DETECTION_COLUMNS.map((c) => (c === "frp" ? "round(frp, 2) AS frp" : c)).join(", ")} FROM read_parquet([${urls.map(q).join(", ")}]) ` +
    `WHERE ${where.join(" AND ")} ORDER BY solar_date, acq_time LIMIT ${MAX_ROWS + 1}`
  );
}

export interface DetectionResult {
  rows: DetectionRow[];
  truncated: boolean;
  bySatellite: Record<string, number>;
}

export async function searchDetections(index: DetectionsIndex, query: DetectionQuery): Promise<DetectionResult> {
  const files = filesFor(index, query);
  if (!files.length) return { rows: [], truncated: false, bySatellite: {} };
  const db = await getDb();
  const conn = await db.connect();
  try {
    const urls = files.map((f) => `${window.location.origin}${f}`);
    const table = await conn.query(buildSql(urls, query));
    let rows = table.toArray().map((r) => {
      const o = r.toJSON() as Record<string, unknown>;
      const row = {} as DetectionRow;
      for (const c of DETECTION_COLUMNS) {
        const v = o[c];
        // DATE columns arrive as epoch milliseconds
        row[c] = (c === "acq_date" || c === "solar_date") && typeof v === "number" ? new Date(v).toISOString().slice(0, 10) : (v as string | number | null);
      }
      return row;
    });
    if (query.ring) rows = rows.filter((r) => pointInRing(Number(r.longitude), Number(r.latitude), query.ring!));
    const truncated = rows.length > MAX_ROWS;
    if (truncated) rows = rows.slice(0, MAX_ROWS);
    const bySatellite: Record<string, number> = {};
    for (const r of rows) bySatellite[String(r.satellite)] = (bySatellite[String(r.satellite)] ?? 0) + 1;
    return { rows, truncated, bySatellite };
  } finally {
    await conn.close();
  }
}
