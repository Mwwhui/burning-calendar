/**
 * Shapes of the static JSON files written by `scripts/export_web.py`.
 * Keep in sync with that script.
 */

export type AreaLevel = "asia" | "group" | "country" | "adm1" | "adm2";

/** [west, south, east, north] in degrees */
export type BBox = [number, number, number, number];

export type PlaybackStep = "year" | "month";

export interface AreaMeta {
  /** URL path of the area: "" (Asia), "southeast-asia", "mys", "mys/sarawak", ... */
  id: string;
  name: string;
  level: AreaLevel;
  parent: string | null;
  children: string[];
  bbox: BBox | null;
  /** a geo/<id>.json file with the borders of the sub-areas exists */
  hasGeo: boolean;
  frames: PlaybackStep[];
  /** an events/<id>.json file exists */
  events?: boolean;
  /** a cells/<iso>.json file exists (countries: own areas can be drawn) */
  cells?: boolean;
  /** a recent/<iso>.json file exists (countries: latest detections) */
  recent?: boolean;
  /** spots/<id>.json: repeat burn spots */
  spots?: boolean;
  /** land/<id>.json: fire inside concessions */
  land?: boolean;
  /** forecast/<id>.json: short-range forecast */
  forecast?: boolean;
  empty?: boolean;
}

export interface AreaIndex {
  generated: string;
  /** last complete day of data (ISO date) */
  lastDay: string | null;
  unit: string;
  /** year -> "El Niño" | "La Niña" */
  enso: Record<string, string>;
  areas: AreaMeta[];
}

export interface MonthlySeries {
  months: string[];
  value: (number | null)[];
  lower: (number | null)[];
  upper: (number | null)[];
  /** converted from an older satellite (not measured by NOAA-20) */
  estimated: boolean[];
  source: string[];
}

export interface AnnualSeries {
  years: number[];
  total: (number | null)[];
  lower: (number | null)[];
  upper: (number | null)[];
  estimatedShare: (number | null)[];
}

export interface Summary {
  peakMonth: number;
  peakShare: number | null;
  busiestYear: number | null;
  busiestYearTotal: number | null;
  busiestYearEstimated: boolean;
  busiestTies: number[];
  partialMonth: string | null;
  thisYear: number;
  throughMonth: number;
  thisYearToDate: number | null;
  rank: number;
  nYears: number;
  pctVsMedian: number | null;
}

export interface ChildChange {
  year: number;
  throughMonth: number;
  baseYears: number[];
  /** child id -> [this year, typical, change %] */
  rows: Record<string, [number | null, number | null, number | null]>;
}

export interface AreaDetail {
  id: string;
  name: string;
  level: AreaLevel;
  series: MonthlySeries;
  annual: AnnualSeries;
  summary: Summary | null;
  notes: { tooFewFrom: string | null; roughYearsPct: number | null };
  childChange: ChildChange | null;
}

export interface PlaybackFrames {
  step: PlaybackStep;
  /** display cell size in degrees */
  deg: number;
  periods: string[];
  totals: (number | null)[];
  /** label of an unfinished last period */
  partial: string | null;
  /** per dot: period index and value (harmonized fire days) */
  p: number[];
  v: number[];
  /** fine cells: dot at the mean position of the detections in a `deg` cell */
  lon?: number[];
  lat?: number[];
  /** coarse grid (older exports): cell centre = ((x + .5) * deg, (y + .5) * deg) */
  x?: number[];
  y?: number[];
}

/** Latest real detections of a country (not converted). */
export interface RecentData {
  lastDay: string;
  sats: string[];
  lon: number[];
  lat: number[];
  /** days before lastDay */
  age: number[];
  frp: (number | null)[];
  sat: number[];
  night: number[];
}

export interface AreaFeatureProps {
  /** sub-area id, null when the border has no data (not navigable) */
  id: string | null;
  name: string;
  km2: number | null;
}

export interface AreaFeatureCollection {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    id: string;
    properties: AreaFeatureProps;
    geometry: GeoJSON.Geometry;
  }[];
}

// ----------------------------------------------------------------------------- detail views

export interface StepInfo {
  donor: string;
  status: string;
  method: string | null;
  fitWindow: (string | null)[] | null;
  monthsFilled: number;
  drift: number | null;
  why: string | null;
  loyo: { method: string; route: string | null; rmse: number | null; bias: number | null; years: number | null }[] | null;
}

export interface Outlook {
  months: number[];
  share: number | null;
  seasonStart: string;
  oni: number | null;
  oniMonth: string;
  lead: number;
  usefulLeads: number[];
  pastExtremes: number;
  skill: { useful: boolean; n: number; hits: number; r: number | null; msss: number | null };
  p_below?: number;
  p_normal?: number;
  p_above?: number;
  normal_low?: number;
  normal_high?: number;
  expected?: number;
  seasons?: { year: number; oni: number | null; total: number | null }[];
}

export interface PeatSplit {
  km2: number | null;
  tooLittle: boolean;
  years?: number[];
  on?: (number | null)[];
  off?: (number | null)[];
}

export interface OfficialCheck {
  spearman: number | null;
  sameTop3: boolean;
  years: number[];
  fireDays: (number | null)[];
  official: (number | null)[];
  sources: string[];
}

export interface GfedCheck {
  first: number;
  last: number;
  rMonthly: number | null;
  rAnomaly: number | null;
  rYearlyRank: number | null;
  top3Fire: number[];
  top3Burned: number[];
  years: number[];
  fireDays: (number | null)[];
  burnedKm2: (number | null)[];
  step2012: number | null;
  step2018: number | null;
  naiveStep2012: number | null;
}

export interface SatDiff {
  years: number[];
  rows: { sat: string; detections: number; vsNoaa20: number | null; night: number | null; weak: number | null }[];
}

export interface AreaExtraDetail {
  raw: { months: string[]; sats: string[]; values: Record<string, (number | null)[]> };
  steps: StepInfo[];
  seams: { rows: { seam: string; stepPct: number | null; placebo: number | null; nPlacebo: number }[]; naiveStep2012: number | null };
  satDiff: SatDiff | null;
  outlook: Outlook | null;
  peat: PeatSplit | null;
  official: OfficialCheck | null;
  gfed: GfedCheck | null;
}

export interface FireEvent {
  id: number;
  start: string;
  end: string;
  days: number;
  km2: number;
  frpMax: number | null;
  peat: number | null;
  lat: number;
  lon: number;
  bbox: BBox;
  where: string;
  /** fire-growth model (scripts/build_growth.py): chance to end >= bigKm2 / last >= longDays */
  pBig?: number | null;
  pLong?: number | null;
  cmp: {
    n: number;
    shareSmaller: number | null;
    biggerBefore: { km2: number; start: string; where: string } | null;
  };
}

/** Where and when one fire event burned (scripts/build_event_dots.py): its ~1 km NOAA-20 cell-days.
 * lon = (gx0 + gx[i] + 0.5) * grid, lat = (gy0 + gy[i] + 0.5) * grid, date = start + d[i] days. Sorted by day. */
export interface EventDots {
  id: number;
  start: string;
  grid: number;
  gx0: number;
  gy0: number;
  gx: number[];
  gy: number[];
  d: number[];
  /** strongest fire radiative power in the cell that day, MW */
  frp: number[];
}

export interface EventsData {
  n: number;
  first: string;
  /** last day of the event record */
  end: string;
  nActive: number;
  lists: { active: number[]; thisYear: number[]; record: number[] };
  events: FireEvent[];
  /** [rank, km²] of all events, biggest first (sampled) */
  sizeCurve: [number, number][];
  growth?: GrowthSummary | null;
}

export interface GrowthTarget {
  usable: boolean;
  p_auc: number | null;
  baseline_auc: number | null;
  p_ap: number | null;
  baseline_ap: number | null;
  p_top1pct_precision: number | null;
  baseline_top1pct_precision: number | null;
  base_rate: number | null;
  n: number | null;
}

export interface GrowthSummary {
  bigKm2: number;
  longDays: number;
  testYears: number[];
  targets: { big?: GrowthTarget; long?: GrowthTarget };
}

export interface DailyData {
  start: string;
  /** per satellite: day offsets from `start` with fire, and their cell-days */
  sats: Record<string, { d: number[]; v: number[] }>;
}

export interface TotalsData {
  column: string;
  sats: string[];
  area: string[];
  month: string[];
  values: Record<string, number[]>;
}

export interface CellsData {
  deg: number;
  months: string[];
  m: number[];
  x: number[];
  y: number[];
  v: number[];
}

/** month ("2019-09") -> [title, url][] */
export type AsmcData = Record<string, [string, string][]>;

// ----------------------------------------------------------------------------- land use

export interface ConcessionFire {
  id: number;
  name: string;
  group: string;
  kind: string;
  km2: number | null;
  bbox: BBox;
  /** harmonized fire days per year (aligned with LandData.years) */
  fireDays: (number | null)[];
  /** NOAA-20 fire days Jan..throughMonth of `year`, and the mean of the same months in baseYears */
  this: number | null;
  typical: number | null;
  changePct: number | null;
}

export interface LandData {
  source: { name: string; credit: string; license: string; note: string };
  years: number[];
  total: (number | null)[];
  inside: (number | null)[];
  year: number;
  throughMonth: number;
  baseYears: number[];
  concessions: ConcessionFire[];
}

export interface SpotsData {
  firstYear: number;
  lastYear: number;
  minYears: number;
  cellsBurned: number;
  /** number of ~2 km cells that burned in 1, 2, ... years */
  histogram: number[];
  truncated: boolean;
  lon: number[];
  lat: number[];
  years: number[];
  /** bit k = burned in firstYear + k */
  mask: number[];
  last: number[];
  cd: number[];
  peat: number[];
  /** concession id or -1 */
  conc: number[];
  concNames: Record<string, string>;
}

export interface ConcessionFeatureCollection {
  type: "FeatureCollection";
  features: {
    type: "Feature";
    id: number;
    properties: { id: number; name: string; group: string; km2: number | null };
    geometry: GeoJSON.Geometry;
  }[];
}

// ----------------------------------------------------------------------------- short-range forecast

export interface ForecastHorizon {
  label: string;
  /** beat both simple forecasts in the backtest; otherwise not shown as a forecast */
  usable: boolean;
  q10: number | null;
  q50: number | null;
  q90: number | null;
  /** usual amount for these dates (climatology of earlier years) */
  usual: number | null;
  pAbove: number | null;
  skillPersist: number | null;
  skillClim: number | null;
  coverage: number | null;
  hit: number | null;
  n: number | null;
}

export interface ForecastData {
  issued: string;
  recentWeek: number | null;
  horizons: { h1: ForecastHorizon; h4: ForecastHorizon };
  history?: {
    targetEnd: string[];
    actual: (number | null)[];
    q10: (number | null)[];
    q50: (number | null)[];
    q90: (number | null)[];
    usual: (number | null)[];
  };
  overall: Record<string, number | string | null>;
  testYears: number[];
  /** the model used weather (it lowered the error in the backtest) */
  weatherUsed?: boolean;
  /** recent weather at the area's fire-weighted point (NASA POWER) */
  weather?: {
    rain30mm: number | null;
    rain30OfUsual: number | null;
    dryDays: number | null;
    soil: number | null;
    soilAnom: number | null;
    tmax7: number | null;
  };
}

// ----------------------------------------------------------------------------- alerts

export interface AlertItem {
  areaId: string;
  name: string;
  level: "watch" | "warning";
  kind: "surge" | "forecast" | "big_fire";
  title: string;
  detail: string;
  value: number | null;
}

export interface AlertsData {
  generated: string;
  lastDay: string | null;
  rules: Record<string, string>;
  alerts: AlertItem[];
}
