"use client";

import * as maplibregl from "maplibre-gl";
import { Layer, Source } from "react-map-gl/maplibre";

import type { HazeView, SatPhoto } from "@/features/explorer/store";
import { colormapLookup, dailyLayer, detailLayers, distLayer, GIBS_CREDIT, hazeLayer, isDistBackground, recolorHaze, type HazeKind } from "@/lib/gibs";
import { AI_COLORMAP, AOD_COLORMAP } from "@/lib/haze-colormaps";

/** A transparent tile: GIBS sometimes answers a missing tile with an error, which should just draw nothing. */
async function blankTile(): Promise<{ data: ArrayBuffer }> {
  const c = new OffscreenCanvas(1, 1);
  return { data: await (await c.convertToBlob({ type: "image/png" })).arrayBuffer() };
}

let registered = false;

/** "gibsdist://" tiles: fetched from GIBS over https with the dark "no disturbance" background made transparent. */
function registerDistProtocol() {
  if (registered) return;
  registered = true;
  maplibregl.addProtocol("gibsdist", async (params, abort) => {
    const r = await fetch(params.url.replace("gibsdist://", "https://"), { signal: abort.signal });
    if (!r.ok) return blankTile();
    const bmp = await createImageBitmap(await r.blob());
    const c = new OffscreenCanvas(bmp.width, bmp.height);
    const ctx = c.getContext("2d")!;
    ctx.drawImage(bmp, 0, 0);
    const img = ctx.getImageData(0, 0, bmp.width, bmp.height);
    const d = img.data;
    for (let i = 0; i < d.length; i += 4) if (isDistBackground(d[i], d[i + 1], d[i + 2])) d[i + 3] = 0;
    ctx.putImageData(img, 0, 0);
    return { data: await (await c.convertToBlob({ type: "image/png" })).arrayBuffer() };
  });
}

// Source and layer ids include the layer and day: a new day mounts a new source before the old one is removed,
// and MapLibre refuses a second source with the same id (the map then kept the first day's tiles).

/**
 * NASA GIBS imagery drawn over the basemap's land and water but under its roads, borders and labels (beforeId)
 * and under the fire layers: the daily photo (true colour or short-wave infrared), 30 m Landsat / Sentinel-2,
 * and OPERA vegetation loss on top.
 */
export function SatelliteLayers({ photo, beforeId }: { photo: SatPhoto; beforeId?: string }) {
  const daily = dailyLayer(photo.date, photo.view ?? "true");
  const detail = photo.detail && (photo.view ?? "true") === "true" ? detailLayers(photo.date) : [];
  const dist = photo.dist ? distLayer(photo.date) : null;
  if (dist) registerDistProtocol();
  return (
    <>
      <Source key={`${daily.id}-${photo.date}`} id={`gibs-daily-${daily.id}-${photo.date}`} type="raster" tiles={daily.tiles} tileSize={256} maxzoom={daily.maxzoom} attribution={GIBS_CREDIT}>
        <Layer id={`gibs-daily-${daily.id}-${photo.date}`} type="raster" beforeId={beforeId} paint={{ "raster-fade-duration": 150 }} />
      </Source>
      {detail.map((l) => (
        <Source key={`${l.id}-${photo.date}`} id={`${l.id}-${photo.date}`} type="raster" tiles={l.tiles} tileSize={256} minzoom={l.minzoom} maxzoom={l.maxzoom}>
          <Layer id={`${l.id}-${photo.date}`} type="raster" beforeId={beforeId} minzoom={9} paint={{ "raster-fade-duration": 150 }} />
        </Source>
      ))}
      {dist && (
        <Source key={`dist-${photo.date}`} id={`gibs-dist-${photo.date}`} type="raster" tiles={dist.tiles} tileSize={256} minzoom={dist.minzoom} maxzoom={dist.maxzoom}>
          <Layer id={`gibs-dist-${photo.date}`} type="raster" beforeId={beforeId} minzoom={8} paint={{ "raster-fade-duration": 150, "raster-opacity": 0.85, "raster-resampling": "nearest" }} />
        </Source>
      )}
    </>
  );
}

const hazeRegistered = new Set<HazeKind>();

/** "gibsaod://" and "gibsai://" tiles: GIBS haze colours turned back into values and redrawn as a violet veil. */
function registerHazeProtocol(kind: HazeKind) {
  if (hazeRegistered.has(kind)) return;
  hazeRegistered.add(kind);
  const scheme = kind === "aod" ? "gibsaod" : "gibsai";
  const lookup = colormapLookup(kind === "aod" ? AOD_COLORMAP : AI_COLORMAP);
  maplibregl.addProtocol(scheme, async (params, abort) => {
    const r = await fetch(params.url.replace(`${scheme}://`, "https://"), { signal: abort.signal });
    if (!r.ok) return blankTile();
    const bmp = await createImageBitmap(await r.blob());
    const c = new OffscreenCanvas(bmp.width, bmp.height);
    const ctx = c.getContext("2d", { willReadFrequently: true })!;
    ctx.drawImage(bmp, 0, 0);
    const img = ctx.getImageData(0, 0, bmp.width, bmp.height);
    recolorHaze(img.data, lookup, kind);
    ctx.putImageData(img, 0, 0);
    return { data: await (await c.convertToBlob({ type: "image/png" })).arrayBuffer() };
  });
}

/**
 * Daily haze or smoke veil, drawn on top of everything (fire included, like real smoke): in fire-heavy areas the fire
 * layer covers nearly all land, so a veil under it was invisible. It is see-through (at most ~75 %), so fire and
 * place names still show; fire layers added later go before the labels and so stay under it.
 */
export function HazeLayer({ haze }: { haze: HazeView }) {
  const l = hazeLayer(haze.date, haze.kind);
  if (!l) return null;
  registerHazeProtocol(haze.kind);
  return (
    <Source key={`${l.id}-${haze.date}`} id={`gibs-haze-${l.id}-${haze.date}`} type="raster" tiles={l.tiles} tileSize={256} maxzoom={l.maxzoom} attribution={GIBS_CREDIT}>
      <Layer id={`gibs-haze-${l.id}-${haze.date}`} type="raster" paint={{ "raster-fade-duration": 150 }} />
    </Source>
  );
}
