import { HeatmapLayer } from "@deck.gl/aggregation-layers";
import type { Layer, PickingInfo } from "@deck.gl/core";
import { GeoJsonLayer, PathLayer, PolygonLayer, ScatterplotLayer, SolidPolygonLayer } from "@deck.gl/layers";

import { interpolatePuRd } from "d3-scale-chromatic";

import { changeColor, clamp01, fireColor, type RGBA } from "@/lib/colors";
import type { AreaFeatureCollection, BBox, ChildChange, ConcessionFeatureCollection, SpotsData } from "@/lib/data/types";
import { dayColor, type Dots } from "@/features/events/lib/dots";
import { cellPolygon, type IndexedFrames } from "@/features/playback/lib/frames";

type Feature = AreaFeatureCollection["features"][number];

/** All deck layers are drawn under the basemap's place labels (interleaved mode). */
export interface Common {
  beforeId?: string;
}

/** `beforeId` is read by @deck.gl/mapbox in interleaved mode but is not in the layer prop types. */
function under(beforeId?: string): object {
  return beforeId ? { beforeId } : {};
}

/** Additive blending: overlapping glows add up to white-hot cores on a dark map. */
const ADDITIVE = {
  blend: true,
  blendColorOperation: "add",
  blendColorSrcFactor: "src-alpha",
  blendColorDstFactor: "one",
  blendAlphaOperation: "add",
  blendAlphaSrcFactor: "one",
  blendAlphaDstFactor: "one-minus-src-alpha",
  depthWriteEnabled: false,
  depthCompare: "always",
} as const;

export interface BorderOptions extends Common {
  geo: AreaFeatureCollection;
  selectedId: string | null;
  hoveredId: string | null;
  dark: boolean;
  /** fill each area by its change vs a typical year */
  change: ChildChange | null;
  pickable: boolean;
  onClick: (id: string) => void;
  onHover: (info: PickingInfo<Feature>) => void;
}

export function bordersLayer(o: BorderOptions): Layer {
  const line: [number, number, number] = o.dark ? [255, 255, 255] : [30, 30, 40];
  const accent: [number, number, number] = [251, 146, 60];
  return new GeoJsonLayer<Feature["properties"]>({
    id: "areas",
    ...under(o.beforeId),
    data: o.geo as unknown as GeoJSON.FeatureCollection,
    pickable: o.pickable,
    stroked: true,
    filled: true,
    lineWidthUnits: "pixels",
    lineJointRounded: true,
    getLineWidth: (f) => {
      const id = f.properties.id;
      if (id && id === o.selectedId) return 2.5;
      if (id && id === o.hoveredId) return 1.8;
      return 0.7;
    },
    getLineColor: (f) => {
      const id = f.properties.id;
      if (id && id === o.selectedId) return [...accent, 255];
      if (id && id === o.hoveredId) return [...line, 230];
      return [...line, f.properties.id ? (o.dark ? 70 : 90) : 30];
    },
    getFillColor: (f) => {
      const id = f.properties.id;
      if (o.change && id) {
        const pct = o.change.rows[id]?.[2];
        if (pct !== null && pct !== undefined) return changeColor(pct, 100, id === o.hoveredId ? 235 : 200);
        return o.dark ? [80, 80, 90, 110] : [200, 200, 205, 140];
      }
      if (id === o.hoveredId) return o.dark ? [255, 255, 255, 22] : [0, 0, 0, 14];
      return [0, 0, 0, 1]; // nearly transparent, but still pickable
    },
    updateTriggers: {
      getLineWidth: [o.selectedId, o.hoveredId],
      getLineColor: [o.selectedId, o.hoveredId, o.dark],
      getFillColor: [o.change, o.hoveredId, o.dark],
    },
    transitions: { getFillColor: 250 },
    onClick: (info) => {
      const id = (info.object as Feature | undefined)?.properties.id;
      if (id) o.onClick(id);
    },
    onHover: (info) => o.onHover(info as PickingInfo<Feature>),
  });
}

export interface FireOptions extends Common {
  frames: IndexedFrames;
  period: number;
  dark: boolean;
  /** height of the densest columns in metres (3D) */
  maxHeight: number;
}

function cellT(o: FireOptions) {
  const { density, maxDensity } = o.frames;
  const logMax = Math.log10(maxDensity + 1);
  return (i: number) => clamp01(Math.log10(density[i] + 1) / logMax);
}

function cellsOf(o: FireOptions): number[] {
  return Array.from(o.frames.byPeriod[o.period] ?? []);
}

/** Glowing dots: one soft dot per cell, size and heat from its fire density. */
export function fireGlowLayers(o: FireOptions): Layer[] {
  const f = o.frames.data;
  const t = cellT(o);
  const data = cellsOf(o);
  // fine (~2 km) dots are drawn a little larger than their cell so neighbours blend
  const metres = f.deg * 111_320 * (f.deg <= 0.05 ? 1.6 : 1);
  const centre = (i: number): [number, number] => [o.frames.lon[i], o.frames.lat[i]];
  const halo = new ScatterplotLayer<number>({
    id: "fire-halo",
    ...under(o.beforeId),
    data,
    getPosition: centre,
    radiusUnits: "meters",
    getRadius: (i) => metres * (o.dark ? 0.5 + 0.8 * t(i) : 0.35 + 0.45 * t(i)),
    radiusMinPixels: 2,
    radiusMaxPixels: 22,
    getFillColor: (i): RGBA => {
      const c = fireColor(0.3 + 0.55 * t(i));
      return [c[0], c[1], c[2], Math.round((o.dark ? 18 : 35) + (o.dark ? 50 : 55) * t(i) ** 1.5)];
    },
    parameters: o.dark ? ADDITIVE : undefined,
    updateTriggers: { getFillColor: [o.frames.maxDensity, o.dark], getRadius: [o.frames.maxDensity, o.dark] },
  });
  const core = new ScatterplotLayer<number>({
    id: "fire-core",
    ...under(o.beforeId),
    data,
    getPosition: centre,
    radiusUnits: "meters",
    getRadius: (i) => metres * (0.18 + 0.32 * t(i)),
    radiusMinPixels: 1,
    radiusMaxPixels: 8,
    getFillColor: (i): RGBA => {
      // cool embers are orange-red, the hottest cells burn yellow
      const c = fireColor(o.dark ? 0.75 - 0.6 * t(i) ** 0.7 : 0.45 + 0.55 * t(i));
      return [c[0], c[1], c[2], Math.round(130 + 125 * t(i))];
    },
    parameters: o.dark ? ADDITIVE : undefined,
    updateTriggers: { getFillColor: [o.frames.maxDensity, o.dark], getRadius: [o.frames.maxDensity] },
  });
  return [halo, core];
}

/** Smooth heat surface (kernel density weighted by fire density). */
export function fireHeatLayer(o: FireOptions): Layer {
  const { density, maxDensity, lon, lat } = o.frames;
  const stops = [0.1, 0.3, 0.5, 0.7, 0.85, 1].map((t) => fireColor(t).slice(0, 3) as [number, number, number]);
  return new HeatmapLayer<number>({
    id: "fire-heat",
    ...under(o.beforeId),
    data: cellsOf(o),
    getPosition: (i) => [lon[i], lat[i]],
    // log weights: a few very dense cells would otherwise wash out everything else
    getWeight: (i) => Math.log10(Math.min(density[i], maxDensity) + 1),
    radiusPixels: 55,
    intensity: 1,
    threshold: 0.03,
    colorRange: stops,
    aggregation: "SUM",
    opacity: 0.8,
    updateTriggers: { getWeight: [maxDensity] },
  });
}

/** 3D columns: one block per cell, height from fire density. */
export function fireColumnsLayer(o: FireOptions): Layer {
  const t = cellT(o);
  const { density, maxDensity } = o.frames;
  return new SolidPolygonLayer<number>({
    id: "fire-columns",
    ...under(o.beforeId),
    data: cellsOf(o),
    getPolygon: (i) => cellPolygon(o.frames, i),
    getFillColor: (i) => fireColor(t(i), 235),
    extruded: true,
    getElevation: (i) => Math.min(density[i] / maxDensity, 1.4) * o.maxHeight,
    material: { ambient: 0.55, diffuse: 0.6, shininess: 20 },
    transitions: { getElevation: 250 },
    updateTriggers: { getFillColor: [maxDensity], getElevation: [maxDensity, o.maxHeight] },
  });
}

/** A drawn own area (closed) or the shape being drawn (open path). */
export function ownAreaLayers(ring: [number, number][], closed: boolean, cursor?: [number, number] | null): Layer[] {
  const accent: [number, number, number] = [56, 189, 248];
  if (closed) {
    return [
      new PolygonLayer({
        id: "own-area",
        data: [{ ring }],
        getPolygon: (d: { ring: [number, number][] }) => d.ring,
        getFillColor: [...accent, 28],
        getLineColor: [...accent, 255],
        lineWidthUnits: "pixels",
        getLineWidth: 2.5,
        stroked: true,
        filled: true,
      }),
    ];
  }
  const path = cursor ? [...ring, cursor] : ring;
  return [
    new PathLayer({
      id: "own-area-draft",
      data: [{ path }],
      getPath: (d: { path: [number, number][] }) => d.path,
      getColor: [...accent, 255],
      widthUnits: "pixels",
      getWidth: 2,
    }),
    new ScatterplotLayer({
      id: "own-area-vertices",
      data: ring,
      getPosition: (p: [number, number]) => p,
      getFillColor: [255, 255, 255, 255],
      getLineColor: [...accent, 255],
      stroked: true,
      lineWidthMinPixels: 2,
      radiusMinPixels: 4,
      getRadius: 1,
    }),
  ];
}

/** Selected fire event: its box and centre. */
export function eventLayers(bbox: BBox, lon: number, lat: number): Layer[] {
  const [w, s, e, n] = bbox;
  const pad = 0.01;
  return [
    new PathLayer({
      id: "event-box",
      data: [
        {
          path: [
            [w - pad, s - pad],
            [e + pad, s - pad],
            [e + pad, n + pad],
            [w - pad, n + pad],
            [w - pad, s - pad],
          ],
        },
      ],
      getPath: (d: { path: [number, number][] }) => d.path,
      getColor: [255, 255, 255, 230],
      widthUnits: "pixels",
      getWidth: 1.5,
    }),
    new ScatterplotLayer({
      id: "event-centre",
      data: [[lon, lat]],
      getPosition: (p: [number, number]) => p,
      getFillColor: [255, 255, 255, 255],
      getLineColor: [239, 68, 68, 255],
      stroked: true,
      lineWidthMinPixels: 3,
      radiusMinPixels: 6,
      getRadius: 1,
    }),
  ];
}

/**
 * Where a fire event burned: its ~1 km squares, pale yellow on its first days to dark red on its last.
 * With `upTo`, only the squares seen by that day; the ones burning that day bright with a dark edge.
 */
export function eventDotsLayer(dots: Dots, upTo: number | null, onHover: (info: PickingInfo<number>) => void): Layer {
  const data: number[] = [];
  for (let i = 0; i < dots.n; i++) if (upTo === null || dots.day[i] <= upTo) data.push(i);
  const h = dots.half * 0.9;
  return new PolygonLayer<number>({
    id: "event-dots",
    data,
    pickable: true,
    getPolygon: (i) => {
      const x = dots.lon[i];
      const y = dots.lat[i];
      return [
        [x - h, y - h],
        [x + h, y - h],
        [x + h, y + h],
        [x - h, y + h],
      ];
    },
    getFillColor: (i) => (upTo === null || dots.day[i] === upTo ? dayColor(dots.day[i], dots.last) : dayColor(dots.day[i], dots.last, 110)),
    stroked: upTo !== null,
    getLineColor: (i) => (dots.day[i] === upTo ? [24, 24, 27, 255] : [0, 0, 0, 0]),
    lineWidthUnits: "pixels",
    getLineWidth: 1.5,
    updateTriggers: { getFillColor: [upTo], getLineColor: [upTo] },
    onHover: (info) => onHover(info as PickingInfo<number>),
  });
}

/**
 * Latest real detections (not converted): small hot dots, newest brightest.
 * Size from fire radiative power, colour from age.
 */
export function recentLayer(
  r: { lon: number[]; lat: number[]; age: number[]; frp: (number | null)[] },
  maxAge: number,
  dark: boolean,
  beforeId?: string,
): Layer[] {
  const data = r.age.map((a, i) => i).filter((i) => r.age[i] <= maxAge);
  const color = (i: number): RGBA => {
    // freshness 1 = seen on the last day: yellow-white; older detections cool to dark red
    const t = 1 - Math.min(1, r.age[i] / Math.max(1, maxAge));
    if (dark && r.age[i] <= 1) return [255, 246, 210, 255];
    const c = fireColor(0.15 + 0.85 * (1 - t));
    return [c[0], c[1], c[2], Math.round(110 + 145 * t)];
  };
  const size = (i: number) => 1.6 + Math.min(4, Math.log10((r.frp[i] ?? 1) + 1) * 1.6);
  return [
    new ScatterplotLayer<number>({
      id: "recent-glow",
      ...under(beforeId),
      data,
      getPosition: (i) => [r.lon[i], r.lat[i]],
      radiusUnits: "pixels",
      getRadius: (i) => size(i) * 2.6,
      getFillColor: (i) => {
        const c = color(i);
        return [c[0], c[1], c[2], dark ? 50 : 40];
      },
      parameters: dark ? ADDITIVE : undefined,
      updateTriggers: { getFillColor: [maxAge, dark] },
    }),
    new ScatterplotLayer<number>({
      id: "recent-core",
      ...under(beforeId),
      data,
      getPosition: (i) => [r.lon[i], r.lat[i]],
      radiusUnits: "pixels",
      getRadius: size,
      getFillColor: color,
      parameters: dark ? ADDITIVE : undefined,
      pickable: false,
      updateTriggers: { getFillColor: [maxAge, dark] },
    }),
  ];
}

function rgb(css: string, alpha: number): RGBA {
  const m = css.match(/\d+/g) ?? ["128", "128", "128"];
  return [Number(m[0]), Number(m[1]), Number(m[2]), alpha];
}

/** Purple scale for "burned in N years" (kept apart from the fire colours). */
export function spotColor(years: number, maxYears: number, alpha = 235): RGBA {
  return rgb(interpolatePuRd(0.35 + 0.65 * clamp01((years - 2) / Math.max(1, maxYears - 2))), alpha);
}

type ConcFeature = ConcessionFeatureCollection["features"][number];

/** Oil palm concession outlines (teal), the picked one highlighted. */
export function concessionsLayer(
  geo: ConcessionFeatureCollection,
  selectedId: number | null,
  hoveredId: number | null,
  onHover: (info: PickingInfo<ConcFeature>) => void,
  onClick: (f: ConcFeature) => void,
): Layer {
  return new GeoJsonLayer({
    id: "concessions",
    data: geo as unknown as GeoJSON.FeatureCollection,
    pickable: true,
    stroked: true,
    filled: true,
    lineWidthUnits: "pixels",
    getLineWidth: (f) => ((f as unknown as ConcFeature).id === selectedId ? 3 : 1.2),
    getLineColor: (f) => ((f as unknown as ConcFeature).id === selectedId ? [13, 148, 136, 255] : [13, 148, 136, 200]),
    getFillColor: (f) => {
      const id = (f as unknown as ConcFeature).id;
      return id === selectedId ? [20, 184, 166, 70] : id === hoveredId ? [20, 184, 166, 55] : [20, 184, 166, 22];
    },
    updateTriggers: { getLineWidth: [selectedId], getLineColor: [selectedId], getFillColor: [selectedId, hoveredId] },
    onHover: (info) => onHover(info as unknown as PickingInfo<ConcFeature>),
    onClick: (info) => info.object && onClick(info.object as unknown as ConcFeature),
  });
}

/** Repeat burn spots: ~2 km cells that burned in many years, darker = more years. */
export function spotsLayer(s: SpotsData, onHover: (info: PickingInfo<number>) => void): Layer {
  const maxYears = s.lastYear - s.firstYear + 1;
  const data = s.years.map((_, i) => i);
  return new ScatterplotLayer<number>({
    id: "spots",
    data,
    pickable: true,
    getPosition: (i) => [s.lon[i], s.lat[i]],
    radiusUnits: "pixels",
    getRadius: (i) => 2.2 + (4 * (s.years[i] - s.minYears)) / Math.max(1, maxYears - s.minYears),
    getFillColor: (i) => spotColor(s.years[i], maxYears),
    stroked: true,
    getLineColor: [255, 255, 255, 200],
    lineWidthMinPixels: 0.6,
    onHover: (info) => onHover(info as PickingInfo<number>),
  });
}
