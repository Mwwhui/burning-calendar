"use client";

import { useCurrentArea } from "@/features/explorer/hooks/use-area";
import { useExplorer } from "@/features/explorer/store";
import { mapContextId } from "@/lib/area";
import { useAreaDetail, usePlaybackFrames } from "@/lib/data/queries";
import { formatDay, formatPeriod, monthSpan } from "@/lib/format";

/** Title, subtitle and legend line describing what the map shows right now (for image export). */
export function useMapCaption() {
  const { index, lookup, area, id } = useCurrentArea();
  const { layer, step, frame, fireStyle, recentDays, ownArea } = useExplorer();
  const { data: frames } = usePlaybackFrames(area ? id : undefined, step, layer === "playback" && !!area?.frames.includes(step));
  const contextId = lookup ? mapContextId(lookup, id) : undefined;
  const { data: ctx } = useAreaDetail(layer === "change" ? contextId : undefined);

  const name = ownArea ? `${ownArea.label} (${area?.name ?? ""})` : area?.name || "Asia";
  let subtitle = "";
  let legend = "";
  if (layer === "playback" && frames) {
    const i = Math.min(frame ?? frames.periods.length - 1, frames.periods.length - 1);
    const total = frames.totals[i];
    subtitle = `Fire activity, ${formatPeriod(frames.periods[i])}${frames.partial === frames.periods[i] ? ` (to ${formatDay(index?.lastDay)})` : ""}: ${
      total === null ? "–" : Math.round(total).toLocaleString("en")
    } fire days (NOAA-20 equivalent)`;
    legend = `Colour: fire days per 1,000 km² (yellow = few, dark red = many). Style: ${
      fireStyle === "glow" ? "dots at the mean position of detections" : fireStyle === "heat" ? "smoothed heat map" : "3D columns"
    }. Years before 2018 are converted from older satellites.`;
  } else if (layer === "change" && ctx?.childChange) {
    const c = ctx.childChange;
    subtitle = `${monthSpan(c.throughMonth)} ${c.year} compared with the same months of ${c.baseYears[0]}–${c.baseYears[c.baseYears.length - 1]}`;
    legend = "Colour: blue = less fire than typical, red = more (NOAA-20 only, no conversion). Grey: too few fires to compare.";
  } else if (layer === "recent") {
    subtitle = `Satellite fire detections, last ${recentDays} day${recentDays > 1 ? "s" : ""} to ${formatDay(index?.lastDay)}`;
    legend = "Each dot is a NOAA-20 VIIRS detection (not converted); newest brightest, size = fire radiative power.";
  }
  return {
    title: `${name} — Burning Calendar`,
    subtitle,
    legend,
    credit: "Data: NASA FIRMS (MODIS, VIIRS), harmonized to NOAA-20. Map: © OpenStreetMap contributors, © CARTO. Not an official product.",
    fileName: (name || "asia").replace(/[^a-zA-Z0-9]+/g, "_").replace(/^_|_$/g, ""),
  };
}
