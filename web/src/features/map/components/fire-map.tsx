"use client";

import "maplibre-gl/dist/maplibre-gl.css";

import type { Layer, PickingInfo } from "@deck.gl/core";
import * as maplibregl from "maplibre-gl";
import { useTheme } from "next-themes";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import MapGL, { NavigationControl, ScaleControl, type MapRef } from "react-map-gl/maplibre";

import { useCurrentArea } from "@/features/explorer/hooks/use-area";
import { useExplorer } from "@/features/explorer/store";
import { indexFrames } from "@/features/playback/lib/frames";
import { ringBBox } from "@/lib/analytics/own-area";
import { areaHref, countryOf, mapContextId, viewBBox } from "@/lib/area";
import { decodeDots, dotDate } from "@/features/events/lib/dots";
import { useAreaDetail, useAreaGeo, useConcessionShapes, useEventDots, usePlaybackFrames, useRecent, useSpots } from "@/lib/data/queries";
import type { AreaFeatureCollection, BBox } from "@/lib/data/types";
import { formatDay, formatInt, formatPct } from "@/lib/format";

import {
  bordersLayer,
  concessionsLayer,
  eventDotsLayer,
  eventLayers,
  fireColumnsLayer,
  fireGlowLayers,
  fireHeatLayer,
  ownAreaLayers,
  recentLayer,
  spotColor,
  spotsLayer,
} from "../lib/layers";
import { DeckOverlay } from "./deck-overlay";
import { DrawBar } from "./draw-bar";
import { HazeLayer, SatelliteLayers } from "./satellite-layers";
import { MapLegend } from "./map-legend";

// MapLibre GL is pinned to v5: deck.gl 9.4's interleaved mode (fire drawn under the
// basemap's labels) reads camera internals that MapLibre v6 changed.

const STYLE = {
  dark: "https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json",
  light: "https://basemaps.cartocdn.com/gl/positron-gl-style/style.json",
};

const ASIA: BBox = [25, -11, 150, 55];
const FIT_PADDING = { top: 64, bottom: 150, left: 32, right: 32 };

type Feature = AreaFeatureCollection["features"][number];
type LngLat = [number, number];

function bboxWidthMetres(b: BBox): number {
  const lat = ((b[1] + b[3]) / 2) * (Math.PI / 180);
  return Math.max(b[2] - b[0], (b[3] - b[1]) * 1.3) * 111_320 * Math.cos(lat);
}

export default function FireMap() {
  const router = useRouter();
  const { resolvedTheme } = useTheme();
  const dark = resolvedTheme === "dark";
  const mapRef = useRef<MapRef>(null);
  const { lookup, area, id } = useCurrentArea();
  const { layer, fireStyle, step, frame, draw, ownArea, event, recentDays, setOwnArea, setDraw } = useExplorer();
  const { showConcessions, showSpots, concession, focus, setConcession, photo, eventDay, haze } = useExplorer();
  const { data: rawDots } = useEventDots(event?.id);
  const dots = useMemo(() => (rawDots && rawDots.id === event?.id ? decodeDots(rawDots) : undefined), [rawDots, event?.id]);
  const { data: concShapes } = useConcessionShapes(showConcessions);
  const { data: spots } = useSpots(showSpots && area?.spots ? id : undefined);
  const countryId = lookup ? countryOf(lookup, id) : undefined;
  const hasRecent = !!countryId && !!lookup?.get(countryId)?.recent;
  const { data: recent } = useRecent(layer === "recent" && hasRecent ? countryId : undefined);

  const contextId = lookup ? mapContextId(lookup, id) : undefined;
  const { data: geo } = useAreaGeo(lookup ? contextId : undefined);
  const { data: contextDetail } = useAreaDetail(layer === "change" ? contextId : undefined);
  const hasFrames = !!area?.frames.includes(step);
  const { data: rawFrames } = usePlaybackFrames(area ? id : undefined, step, layer === "playback" && hasFrames);
  const frames = useMemo(() => (rawFrames ? indexFrames(rawFrames) : undefined), [rawFrames]);

  const [hover, setHover] = useState<{ x: number; y: number; f: Feature } | null>(null);
  const downAt = useRef<[number, number] | null>(null);
  /** hover on an overlay (concession, repeat spot): shown instead of the area tooltip */
  const [tip, setTip] = useState<{ x: number; y: number; title: string; lines: string[]; id?: number } | null>(null);
  const [labelId, setLabelId] = useState<string | undefined>();
  /** first road / border line of the basemap: the satellite photo goes under it */
  const [lineId, setLineId] = useState<string | undefined>();
  const [draft, setDraft] = useState<LngLat[]>([]);
  const [cursor, setCursor] = useState<LngLat | null>(null);
  const bbox: BBox = area?.bbox ? viewBBox(area.bbox) : ASIA;

  const fit = useCallback((b: BBox, maxZoom = 10) => {
    mapRef.current?.fitBounds(
      [
        [b[0], b[1]],
        [b[2], b[3]],
      ],
      { padding: FIT_PADDING, duration: 900, maxZoom },
    );
  }, []);

  // fly to the area whenever it changes
  useEffect(() => {
    if (area?.bbox) fit(viewBBox(area.bbox));
  }, [area?.id, area?.bbox, fit]);

  useEffect(() => {
    if (ownArea) fit(ringBBox(ownArea.ring), 11);
  }, [ownArea, fit]);

  useEffect(() => {
    if (event) fit([event.bbox[0] - 0.05, event.bbox[1] - 0.05, event.bbox[2] + 0.05, event.bbox[3] + 0.05], 12);
  }, [event, fit]);

  useEffect(() => {
    if (concession) fit([concession.bbox[0] - 0.02, concession.bbox[1] - 0.02, concession.bbox[2] + 0.02, concession.bbox[3] + 0.02], 12);
  }, [concession, fit]);

  useEffect(() => {
    if (focus) fit([focus.lon - 0.08, focus.lat - 0.08, focus.lon + 0.08, focus.lat + 0.08], 12);
  }, [focus, fit]);

  useEffect(() => {
    mapRef.current?.easeTo({ pitch: fireStyle === "columns" && layer === "playback" ? 50 : 0, duration: 700 });
  }, [fireStyle, layer]);

  const setCaptureMap = useExplorer((s) => s.setCaptureMap);
  useEffect(() => {
    setCaptureMap(() => {
      const m = mapRef.current?.getMap();
      if (!m) return null;
      try {
        return m.getCanvas().toDataURL("image/png");
      } catch {
        return null; // tainted canvas (should not happen with CORS-enabled CARTO tiles)
      }
    });
    return () => setCaptureMap(null);
  }, [setCaptureMap]);

  /** first label layer of the basemap: deck layers go under it so place names stay readable */
  const findLabels = useCallback(() => {
    const style = mapRef.current?.getMap().getStyle();
    setLabelId(style?.layers.find((l) => l.type === "symbol")?.id);
    setLineId(style?.layers.find((l) => l.type === "line" && !l.id.startsWith("gibs"))?.id);
  }, []);

  const period = frames ? Math.min(frame ?? frames.data.periods.length - 1, frames.data.periods.length - 1) : 0;
  const selectedId = area && !area.hasGeo ? area.id : null;

  function stopDrawing() {
    setDraft([]);
    setCursor(null);
    setDraw("off");
  }

  function finish(ring: LngLat[]) {
    if (ring.length < 3 || !area || !lookup) return;
    const countryId = countryOf(lookup, area.id);
    if (!countryId) return;
    setOwnArea({ ring, countryId, label: draw === "rectangle" ? "Drawn rectangle" : "Drawn shape" });
    setDraft([]);
    setCursor(null);
  }

  function onMapClick(e: maplibregl.MapMouseEvent) {
    if (draw === "off") return;
    const p: LngLat = [e.lngLat.lng, e.lngLat.lat];
    if (draw === "rectangle") {
      if (draft.length === 0) setDraft([p]);
      else {
        const [a] = draft;
        finish([a, [p[0], a[1]], p, [a[0], p[1]]]);
      }
      return;
    }
    // click near the first point closes the shape
    const first = draft[0];
    const m = mapRef.current?.getMap();
    if (first && m && draft.length >= 3) {
      const a = m.project(first);
      const b = m.project(p);
      if (Math.hypot(a.x - b.x, a.y - b.y) < 12) {
        finish(draft);
        return;
      }
    }
    setDraft([...draft, p]);
  }

  const layers = useMemo(() => {
    const out: Layer[] = [];
    const common = { beforeId: labelId };
    // a picked fire event shows its own squares: the area-wide fire would hide them
    const hideFire = !!photo?.hideFire || !!(event && dots);
    if (layer === "playback" && frames && !hideFire) {
      const o = { ...common, frames, period, dark, maxHeight: bboxWidthMetres(bbox) * 0.12 };
      if (fireStyle === "glow") out.push(...fireGlowLayers(o));
      else if (fireStyle === "heat") out.push(fireHeatLayer(o));
      else out.push(fireColumnsLayer(o));
    }
    if (geo) {
      out.push(
        bordersLayer({
          ...common,
          geo,
          selectedId,
          hoveredId: hover?.f.properties.id ?? null,
          dark,
          pickable: draw === "off",
          change: layer === "change" ? (contextDetail?.childChange ?? null) : null,
          onClick: (cid) => router.push(areaHref(cid)),
          onHover: (info: PickingInfo<Feature>) =>
            setHover(info.object ? { x: info.x, y: info.y, f: info.object } : null),
        }),
      );
    }
    if (layer === "recent" && recent && !hideFire) out.push(...recentLayer(recent, recentDays, dark, labelId));
    if (showConcessions && concShapes) {
      out.push(
        concessionsLayer(
          concShapes,
          concession?.id ?? null,
          tip?.id ?? null,
          (info) =>
            setTip(
              info.object
                ? {
                    x: info.x,
                    y: info.y,
                    id: info.object.id,
                    title: info.object.properties.name,
                    lines: [
                      `Oil palm concession${info.object.properties.group ? ` · ${info.object.properties.group}` : ""}`,
                      info.object.properties.km2 ? `${formatInt(info.object.properties.km2)} km²` : "",
                    ].filter(Boolean),
                  }
                : null,
            ),
          (f) => {
            const b = f.properties as unknown as { id: number };
            const bb = concShapes.features.find((x) => x.id === b.id);
            if (bb) setConcession({ id: b.id, bbox: geomBBox(bb.geometry) });
          },
        ),
      );
    }
    if (showSpots && spots) {
      out.push(
        spotsLayer(spots, (info) => {
          const i = info.object;
          if (i === undefined || i === null) return setTip(null);
          const n = spots.lastYear - spots.firstYear + 1;
          const extra = [spots.peat[i] ? "on mapped peat" : "", spots.conc[i] >= 0 ? `in ${spots.concNames[String(spots.conc[i])] ?? "a concession"}` : ""].filter(Boolean);
          setTip({
            x: info.x,
            y: info.y,
            title: `Burned in ${spots.years[i]} of ${n} years`,
            lines: [`last in ${spots.last[i]} · ${spots.cd[i]} fire days since ${spots.firstYear}`, ...extra],
          });
        }),
      );
    }
    if (ownArea) out.push(...ownAreaLayers(ownArea.ring, true));
    if (draw !== "off" && draft.length) {
      if (draw === "rectangle" && cursor) {
        const [a] = draft;
        out.push(...ownAreaLayers([a, [cursor[0], a[1]], cursor, [a[0], cursor[1]], a], false));
      } else {
        out.push(...ownAreaLayers(draft, false, cursor));
      }
    }
    if (event && dots) {
      out.push(
        eventDotsLayer(dots, eventDay, (info) => {
          const i = info.object;
          if (i === undefined || i === null) return setTip(null);
          const n = dots.last + 1;
          setTip({
            x: info.x,
            y: info.y,
            title: `Fire seen ${formatDay(dotDate(dots, dots.day[i]))}`,
            lines: [`day ${dots.day[i] + 1} of ${n} of this fire`, `strongest ${formatInt(dots.frp[i])} MW (NOAA-20, ~1 km square)`],
          });
        }),
      );
    }
    if (event) out.push(...eventLayers(event.bbox, event.lon, event.lat));
    return out;
  }, [dots, eventDay, photo?.hideFire, layer, frames, period, dark, bbox, fireStyle, geo, selectedId, hover, draw, contextDetail, router, ownArea, draft, cursor, event, labelId, recent, recentDays, showConcessions, concShapes, concession, tip, showSpots, spots, setConcession]);

  const change = layer === "change" ? contextDetail?.childChange : null;
  const hoverRow = hover?.f.properties.id && change ? change.rows[hover.f.properties.id] : undefined;

  return (
    <div
      className="relative h-full w-full"
      // Open the area under the pointer on a plain click (not a drag). The border layer's own deck.gl click
      // does not reach us in interleaved mode, but its hover pick does, so the click uses the hovered area.
      onPointerDown={(e) => {
        downAt.current = [e.clientX, e.clientY];
      }}
      onClick={(e) => {
        const d = downAt.current;
        const id = hover?.f.properties.id;
        if (draw !== "off" || !id || (e.target as HTMLElement).tagName !== "CANVAS") return;
        if (d && Math.hypot(e.clientX - d[0], e.clientY - d[1]) > 5) return;
        router.push(areaHref(id));
      }}
      onMouseLeave={() => {
        setHover(null);
        setTip(null);
      }}
    >
      <MapGL
        ref={mapRef}
        mapLib={maplibregl}
        // keep the last frame readable so "Save map image" can copy it (deck draws into the same canvas)
        canvasContextAttributes={{ preserveDrawingBuffer: true }}
        initialViewState={{ bounds: [bbox[0], bbox[1], bbox[2], bbox[3]], fitBoundsOptions: { padding: 40 } }}
        mapStyle={dark ? STYLE.dark : STYLE.light}
        attributionControl={{ compact: true }}
        dragRotate={fireStyle === "columns"}
        doubleClickZoom={draw === "off"}
        style={{ position: "absolute", inset: 0 }}
        cursor={draw !== "off" ? "crosshair" : hover?.f.properties.id ? "pointer" : "grab"}
        onLoad={findLabels}
        onStyleData={findLabels}
        onClick={onMapClick}
        // GIBS answers days without a Landsat / Sentinel-2 pass with an error tile: not worth a console error
        onError={(e) => {
          const msg = String((e.error as Error | undefined)?.message ?? "");
          if (!msg.includes("gibs.earthdata") && !String((e as { sourceId?: string }).sourceId ?? "").startsWith("HLS")) console.error(e.error);
        }}
        onDblClick={() => draw === "polygon" && finish(draft)}
        onMouseMove={(e) => {
          if (draw !== "off" && draft.length) setCursor([e.lngLat.lng, e.lngLat.lat]);
        }}
      >
        {photo && lineId && <SatelliteLayers photo={photo} beforeId={lineId} />}
        {haze && lineId && <HazeLayer haze={haze} />}
        <DeckOverlay layers={layers} interleaved />
        <NavigationControl position="top-right" showCompass={fireStyle === "columns"} />
        <ScaleControl position="bottom-left" maxWidth={90} />
      </MapGL>

      {tip && draw === "off" && (
        <div
          className="pointer-events-none absolute z-10 rounded-md border bg-popover/95 px-2.5 py-1.5 text-xs shadow-lg backdrop-blur"
          style={{ left: tip.x + 14, top: tip.y + 14 }}
        >
          <div className="font-medium">{tip.title}</div>
          {tip.lines.map((l) => (
            <div key={l} className="text-muted-foreground">
              {l}
            </div>
          ))}
        </div>
      )}

      {hover && !tip && draw === "off" && (
        <div
          className="pointer-events-none absolute z-10 rounded-md border bg-popover/95 px-2.5 py-1.5 text-xs shadow-lg backdrop-blur"
          style={{ left: hover.x + 14, top: hover.y + 14 }}
        >
          <div className="font-medium">{hover.f.properties.name}</div>
          {hoverRow && (
            <div className="text-muted-foreground">
              {formatInt(hoverRow[0])} fire days ·{" "}
              {hoverRow[2] === null ? "too few to compare" : `${formatPct(hoverRow[2])} vs typical`}
            </div>
          )}
          <div className="text-muted-foreground">{hover.f.properties.id ? "Click to open" : "No data"}</div>
        </div>
      )}

      {draw !== "off" && (
        <DrawBar
          mode={draw}
          points={draft.length}
          onFinish={() => finish(draft)}
          onUndo={() => setDraft(draft.slice(0, -1))}
          onCancel={stopDrawing}
        />
      )}

      <MapLegend layer={layer} fireStyle={fireStyle} maxDensity={frames?.maxDensity} change={change ?? null} />
      {showSpots && spots && (
        <div className="pointer-events-none absolute right-3 bottom-[232px] z-10 w-48 rounded-lg border bg-background/80 px-2.5 py-2 text-[10.5px] shadow-md backdrop-blur-md max-sm:hidden">
          <div className="mb-1.5 font-medium">Repeat spots: years with fire</div>
          <div
            className="h-1.5 w-full rounded-full"
            style={{
              background: `linear-gradient(to right, ${[3, 6, 9, 12, 15]
                .map((y) => `rgb(${spotColor(y, spots.lastYear - spots.firstYear + 1).slice(0, 3).join(",")})`)
                .join(", ")})`,
            }}
          />
          <div className="mt-1 flex justify-between text-muted-foreground">
            <span>{spots.minYears}</span>
            <span>
              {spots.lastYear - spots.firstYear + 1} of {spots.lastYear - spots.firstYear + 1} years
            </span>
          </div>
        </div>
      )}
    </div>
  );
}

/** Bounding box of a GeoJSON polygon or multipolygon. */
function geomBBox(g: GeoJSON.Geometry): BBox {
  const pts: number[][] = [];
  const walk = (c: unknown): void => {
    if (Array.isArray(c) && typeof c[0] === "number") pts.push(c as number[]);
    else if (Array.isArray(c)) c.forEach(walk);
  };
  walk((g as { coordinates?: unknown }).coordinates);
  const xs = pts.map((p) => p[0]);
  const ys = pts.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
