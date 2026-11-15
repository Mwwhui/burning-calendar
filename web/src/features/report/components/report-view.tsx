"use client";

import { Printer } from "lucide-react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Note } from "@/components/common/section";
import { Button } from "@/components/ui/button";
import { fireBrief } from "@/features/area-summary/lib/brief";
import { Headline, Metrics } from "@/features/area-summary/components/metrics";
import { CalendarHeatmap } from "@/features/calendar/components/calendar-heatmap";
import { ForecastCard } from "@/features/forecast/components/forecast-view";
import { CumulativeChart, YearlyBars } from "@/features/trends/components/trends-view";
import { ancestry, areaHref, buildLookup, inAsia, LEVEL_LABEL } from "@/lib/area";
import { useAreaDetail, useAreaIndex } from "@/lib/data/queries";
import { formatDay } from "@/lib/format";

/** sessionStorage key for the map image the explorer saves before opening the report */
export const REPORT_MAP_KEY = "burning-calendar:report-map";

/**
 * Printable one-area report (challenge: "download analytics and visualizations").
 * Opens the browser's print dialog; "Save as PDF" gives a PDF with sharp text and charts.
 */
export function ReportView() {
  const params = useSearchParams();
  const id = params.get("id") ?? "";
  const { data: index } = useAreaIndex();
  const lookup = useMemo(() => (index ? buildLookup(index) : undefined), [index]);
  const area = lookup?.get(id);
  const { data: detail } = useAreaDetail(area && !area.empty ? id : undefined);
  // the map image saved by the explorer (shown only after the record loads, so no hydration mismatch)
  const [map] = useState<string | null>(() => {
    if (typeof window === "undefined") return null;
    try {
      return sessionStorage.getItem(REPORT_MAP_KEY);
    } catch {
      return null;
    }
  });

  // open the print dialog once everything has drawn
  useEffect(() => {
    if (!detail || params.get("print") !== "1") return;
    const t = window.setTimeout(() => window.print(), 1500);
    return () => window.clearTimeout(t);
  }, [detail, params]);

  if (!index || !lookup) return <p className="p-8 text-sm text-muted-foreground">Loading…</p>;
  if (!area) return <p className="p-8 text-sm">Unknown area.</p>;
  const s = detail?.summary ?? null;
  const trail = ancestry(lookup, id).slice(0, -1).map((a) => a.name).join(" › ");

  return (
    <main className="flex-1 overflow-y-auto bg-white text-neutral-900">
      <div className="report-page mx-auto max-w-[800px] space-y-6 px-6 py-8 text-[13px] leading-relaxed">
        <div data-print-hide className="flex items-center justify-between gap-2">
          <Link href={areaHref(id)} className="text-sm underline">
            ← Back to the map
          </Link>
          <Button size="sm" onClick={() => window.print()}>
            <Printer /> Print / Save as PDF
          </Button>
        </div>

        <header className="space-y-1 border-b pb-3">
          <div className="text-xs text-neutral-500">
            Burning Calendar · fire activity report · {LEVEL_LABEL[area.level]}
            {trail ? ` in ${trail}` : ""}
          </div>
          <h1 className="text-3xl font-semibold tracking-tight">{area.name}</h1>
          <div className="text-xs text-neutral-500">
            Data: NASA FIRMS to {formatDay(index.lastDay)} · report made {formatDay(new Date().toISOString().slice(0, 10))}
          </div>
          {s && <Headline s={s} />}
        </header>

        {!detail && <p className="text-neutral-500">Loading the record…</p>}
        {detail && (
          <>
            {s && <Metrics s={s} unit={index.unit} />}
            {s && (
              <section className="space-y-1.5">
                {fireBrief(area.name, s, index.unit, index.enso[String(s.thisYear)], inAsia(lookup, area.id)).map((p) => (
                  <p key={p}>{p}</p>
                ))}
              </section>
            )}
            {area.forecast && <ForecastCard areaId={id} />}
            {map && (
              <section className="space-y-1">
                <h2 className="text-base font-semibold">Map</h2>
                {/* eslint-disable-next-line @next/next/no-img-element */}
                <img src={map} alt={`Map of fire activity in ${area.name}`} className="w-full rounded border" />
              </section>
            )}
            <section className="report-break space-y-2">
              <h2 className="text-base font-semibold">Fire calendar (fire days per month)</h2>
              <div className="@container">
                <CalendarHeatmap series={detail.series} partialMonth={s?.partialMonth ?? null} enso={index.enso} initialSpan="all" printMode />
              </div>
            </section>
            <section className="report-break space-y-6">
              {s && <CumulativeChart series={detail.series} summary={s} enso={index.enso} />}
              <YearlyBars annual={detail.annual} />
            </section>
            <section className="space-y-1 border-t pt-3">
              <h2 className="text-sm font-semibold">About these numbers</h2>
              <Note>
                Unit: fire days, ~1 km cells with at least one satellite fire detection on a local day, in NOAA-20 VIIRS terms.
                MODIS (2000–2011) and Suomi NPP (2012–2018) months are converted to NOAA-20 terms and carry a likely range;
                NOAA-20 months (from April 2018) are measured. Satellites miss fires under thick cloud or smoke, small fires
                under trees and smouldering peat. Not an official product: for decisions use national agencies and the ASEAN
                Specialised Meteorological Centre.
              </Note>
              <Note>
                Data: NASA FIRMS (MODIS C6.1, VIIRS 375 m); borders geoBoundaries; ENSO NOAA ONI. Cite as: Burning Calendar,
                harmonized MODIS–VIIRS fire record for {area.name}, data to {formatDay(index.lastDay)}.
              </Note>
            </section>
          </>
        )}
      </div>
    </main>
  );
}
