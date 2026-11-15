"use client";

import { ArrowUpLeft, Box, Camera, Crosshair, Flame, Pentagon, Radio, Repeat, Satellite, Haze, Sparkles, Square, Thermometer, TreePalm, TrendingUp } from "lucide-react";
import { useState } from "react";
import Link from "next/link";

import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { CoordsDialog } from "@/features/map/components/coords-dialog";
import { latestPhotoDay } from "@/features/map/components/photo-bar";
import { useMapCaption } from "@/features/map/hooks/use-map-caption";
import { composeMapImage, downloadDataUrl } from "@/lib/image-export";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { areaHref, countryOf } from "@/lib/area";
import { shiftDay } from "@/lib/gibs";
import { cn } from "@/lib/utils";

import { useCurrentArea } from "../hooks/use-area";
import { useExplorer, type DrawMode, type FireStyle, type MapLayer } from "../store";

/** Day the haze map opens on: the satellite photo's day, else the picked fire's chosen or last day, else yesterday. */
function hazeStartDay(photoDate: string | undefined, event: { start: string; end: string } | null, eventDay: number | null): string {
  const max = latestPhotoDay();
  const d = photoDate ?? (event ? (eventDay !== null ? shiftDay(event.start, eventDay) : event.end) : max);
  return d > max ? max : d;
}

const GLASS = "rounded-lg border bg-background/85 shadow-md backdrop-blur-md";

function Tip({ label, children }: { label: string; children: React.ReactElement }) {
  return (
    <Tooltip>
      <TooltipTrigger render={children} />
      <TooltipContent side="bottom">{label}</TooltipContent>
    </Tooltip>
  );
}

/** Floating controls over the map: what to show, how to draw fire, own areas, "up one level". */
export function MapToolbar() {
  const { layer, fireStyle, draw, ownArea, setLayer, setFireStyle, setDraw, setOwnArea } = useExplorer();
  const { area, lookup, id } = useCurrentArea();
  const parent = area?.parent !== null && area?.parent !== undefined ? lookup?.get(area.parent) : undefined;
  const cid = lookup ? countryOf(lookup, id) : undefined;
  const canDraw = !!cid && !!lookup?.get(cid)?.cells;
  const hasRecent = !!cid && !!lookup?.get(cid)?.recent;
  const [coords, setCoords] = useState(false);
  const caption = useMapCaption();
  const captureMap = useExplorer((s) => s.captureMap);

  async function saveMap() {
    const raw = captureMap?.();
    if (!raw) return;
    const png = await composeMapImage(raw, caption);
    downloadDataUrl(`map_${caption.fileName}.png`, png);
  }
  const { showConcessions, showSpots, setShowConcessions, setShowSpots, photo, setPhoto, event, haze, setHaze, eventDay } = useExplorer();
  const hasLand = !!area?.land || (!!cid && !!lookup?.get(cid)?.land);
  const hasSpots = !!area?.spots;

  return (
    <div className="pointer-events-none absolute top-3 left-3 z-10 flex max-w-[calc(100%-4.5rem)] flex-wrap items-center gap-2 [&>*]:pointer-events-auto">
      <ToggleGroup variant="outline" size="sm" spacing={0} className={GLASS} value={[layer]} onValueChange={(v) => v[0] && setLayer(v[0] as MapLayer)}>
        <ToggleGroupItem value="playback" className="gap-1.5 px-3">
          <Flame className="size-3.5" /> Fire
        </ToggleGroupItem>
        <ToggleGroupItem value="change" className="gap-1.5 px-3">
          <TrendingUp className="size-3.5" /> <span className="max-lg:hidden">This year vs typical</span><span className="lg:hidden">vs typical</span>
        </ToggleGroupItem>
        {hasRecent && (
          <ToggleGroupItem value="recent" className="gap-1.5 px-3">
            <Radio className="size-3.5" /> Latest fires
          </ToggleGroupItem>
        )}
      </ToggleGroup>

      {layer === "playback" && (
        <ToggleGroup variant="outline" size="sm" spacing={0} className={GLASS} value={[fireStyle]} onValueChange={(v) => v[0] && setFireStyle(v[0] as FireStyle)}>
          <Tip label="Glowing dots">
            <ToggleGroupItem value="glow" aria-label="Glowing dots" className="px-2">
              <Sparkles className="size-3.5" />
            </ToggleGroupItem>
          </Tip>
          <Tip label="Heat map (smoothed)">
            <ToggleGroupItem value="heat" aria-label="Heat map" className="px-2">
              <Thermometer className="size-3.5" />
            </ToggleGroupItem>
          </Tip>
          <Tip label="3D columns (right-drag to tilt)">
            <ToggleGroupItem value="columns" aria-label="3D columns" className="px-2">
              <Box className="size-3.5" />
            </ToggleGroupItem>
          </Tip>
        </ToggleGroup>
      )}

      {canDraw && (
        <ToggleGroup
          variant="outline"
          size="sm"
          spacing={0}
          className={GLASS}
          value={draw === "off" ? [] : [draw]}
          onValueChange={(v) => setDraw((v[0] as DrawMode) ?? "off")}
        >
          <Tip label="Draw a rectangle (your own area)">
            <ToggleGroupItem value="rectangle" aria-label="Draw a rectangle" className="gap-1.5 px-2.5">
              <Square className="size-3.5" /> <span className="max-md:hidden">Draw</span>
            </ToggleGroupItem>
          </Tip>
          <Tip label="Draw any shape (click corners)">
            <ToggleGroupItem value="polygon" aria-label="Draw a shape" className="px-2">
              <Pentagon className="size-3.5" />
            </ToggleGroupItem>
          </Tip>
        </ToggleGroup>
      )}
      {canDraw && (
        <Tip label="Area from coordinates (circle or box)">
          <button
            type="button"
            aria-label="Area from coordinates"
            onClick={() => setCoords(true)}
            className={cn(GLASS, "inline-flex h-7 items-center px-2 hover:bg-muted")}
          >
            <Crosshair className="size-3.5" />
          </button>
        </Tip>
      )}
      <Tip label="Real satellite photo of a day (NASA)">
        <button
          type="button"
          aria-pressed={!!photo}
          onClick={() => setPhoto(photo ? null : { date: event ? event.end : latestPhotoDay(), detail: true })}
          className={cn(GLASS, "inline-flex h-7 items-center gap-1 px-2.5 text-[0.8rem] hover:bg-muted", photo && "border-sky-600 bg-sky-600 text-white hover:bg-sky-700")}
        >
          <Satellite className="size-3.5" /> <span className="max-md:hidden">Satellite</span>
        </button>
      </Tip>
      <Tip label="Haze and smoke of a day (NASA)">
        <button
          type="button"
          aria-pressed={!!haze}
          onClick={() => setHaze(haze ? null : { date: hazeStartDay(photo?.date, event, eventDay), kind: "aod" })}
          className={cn(GLASS, "inline-flex h-7 items-center gap-1 px-2.5 text-[0.8rem] hover:bg-muted", haze && "border-foreground bg-foreground text-background hover:bg-foreground/85")}
        >
          <Haze className="size-3.5" /> <span className="max-md:hidden">Haze</span>
        </button>
      </Tip>
      <CoordsDialog open={coords} onOpenChange={setCoords} />
      <Tip label="Save the map as an image (PNG, with title and legend)">
        <button
          type="button"
          aria-label="Save map image"
          onClick={saveMap}
          className={cn(GLASS, "inline-flex h-7 items-center px-2 hover:bg-muted")}
        >
          <Camera className="size-3.5" />
        </button>
      </Tip>
      {(hasLand || hasSpots) && (
        <div className={cn(GLASS, "flex h-7 items-center overflow-hidden text-[0.8rem]")}>
          {hasLand && (
            <Tip label="Mapped oil palm concessions (Sarawak)">
              <button
                type="button"
                aria-pressed={showConcessions}
                onClick={() => setShowConcessions(!showConcessions)}
                className={cn("inline-flex h-full items-center gap-1 px-2.5 hover:bg-muted", showConcessions && "bg-teal-500/15 text-teal-700 dark:text-teal-300")}
              >
                <TreePalm className="size-3.5" /> <span className="max-md:hidden">Concessions</span>
              </button>
            </Tip>
          )}
          {hasSpots && (
            <Tip label="Places that burn year after year (since 2012)">
              <button
                type="button"
                aria-pressed={showSpots}
                onClick={() => setShowSpots(!showSpots)}
                className={cn("inline-flex h-full items-center gap-1 border-l px-2.5 hover:bg-muted", showSpots && "bg-fuchsia-500/15 text-fuchsia-700 dark:text-fuchsia-300")}
              >
                <Repeat className="size-3.5" /> <span className="max-md:hidden">Repeat spots</span>
              </button>
            </Tip>
          )}
        </div>
      )}

      {ownArea ? (
        <button
          type="button"
          onClick={() => setOwnArea(null)}
          className={cn(GLASS, "inline-flex h-7 items-center gap-1 px-2.5 text-[0.8rem] hover:bg-muted")}
        >
          <ArrowUpLeft className="size-3.5" /> Back to {area?.name}
        </button>
      ) : (
        parent && (
          <Link href={areaHref(parent.id)} className={cn(GLASS, "inline-flex h-7 items-center gap-1 px-2.5 text-[0.8rem] hover:bg-muted")}>
            <ArrowUpLeft className="size-3.5" /> {parent.name}
          </Link>
        )
      )}
    </div>
  );
}
