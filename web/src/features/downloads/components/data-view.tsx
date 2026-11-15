"use client";

import { Download, FileJson, FileText, ImageDown, Table } from "lucide-react";
import { useQueryClient } from "@tanstack/react-query";

import { Note, Section } from "@/components/common/section";
import { Button } from "@/components/ui/button";
import { download, safeName, toCsv } from "@/lib/csv";
import { dataUrl } from "@/lib/data/paths";
import type { AreaDetail, AreaFeatureCollection, AreaMeta, TotalsData } from "@/lib/data/types";

import { useExplorer } from "@/features/explorer/store";
import { REPORT_MAP_KEY } from "@/features/report/components/report-view";

import { DetectionsDownload } from "./detections-download";

/** Downloads: monthly and yearly record, raw totals per sub-area, GIS layer, print (app.py "data" tab). */
export function DataView({
  detail,
  area,
  own,
  lastDay,
}: {
  detail: AreaDetail;
  area: AreaMeta | undefined;
  own: boolean;
  lastDay: string | null;
}) {
  const qc = useQueryClient();
  const name = safeName(own ? `my_area_${detail.name}` : detail.name);

  function monthly() {
    const s = detail.series;
    download(
      `monthly_${name}.csv`,
      toCsv(
        ["month", "harmonized", "lower", "upper", "estimated", "source"],
        s.months.map((m, i) => [m, s.value[i]?.toFixed(1), s.lower[i]?.toFixed(1), s.upper[i]?.toFixed(1), s.estimated[i], s.source[i]]),
      ),
    );
  }

  function yearly() {
    const a = detail.annual;
    download(
      `yearly_${name}.csv`,
      toCsv(
        ["year", "total", "lower", "upper", "estimated_share"],
        a.years.map((y, i) => [y, a.total[i]?.toFixed(1), a.lower[i]?.toFixed(1), a.upper[i]?.toFixed(1), a.estimatedShare[i]]),
      ),
    );
  }

  async function totals() {
    if (!area) return;
    const t = await qc.fetchQuery<TotalsData>({
      queryKey: ["totals", area.id],
      queryFn: () => fetch(dataUrl.totals(area.id)).then((r) => r.json()),
    });
    download(
      `totals_by_area_${name}.csv`,
      toCsv([t.column, "month", ...t.sats], t.area.map((a, i) => [a, t.month[i], ...t.sats.map((s) => t.values[s][i])])),
    );
  }

  async function geojson() {
    if (!area) return;
    const geo = await qc.fetchQuery<AreaFeatureCollection>({
      queryKey: ["geo", area.id],
      queryFn: () => fetch(dataUrl.geo(area.id)).then((r) => r.json()),
    });
    const ch = detail.childChange;
    const out = {
      type: "FeatureCollection",
      features: geo.features.map((f) => {
        const r = f.properties.id && ch ? ch.rows[f.properties.id] : undefined;
        return {
          type: "Feature",
          geometry: f.geometry,
          properties: {
            name: f.properties.name,
            km2: f.properties.km2,
            fire_days: r?.[0] ?? null,
            normal: r?.[1] ?? null,
            change_pct: r?.[2] ?? null,
            year: ch?.year ?? null,
            through_month: ch?.throughMonth ?? null,
          },
        };
      }),
    };
    download(`areas_${name}.geojson`, JSON.stringify(out), "application/geo+json");
  }

  const captureMap = useExplorer((st) => st.captureMap);

  function openReport() {
    if (!area) return;
    try {
      const png = captureMap?.();
      if (png) sessionStorage.setItem(REPORT_MAP_KEY, png);
      else sessionStorage.removeItem(REPORT_MAP_KEY);
    } catch {
      // storage full or blocked: the report is made without the map
    }
    window.open(`/report/?id=${encodeURIComponent(area.id)}&print=1`, "_blank");
  }

  const hasSub = !own && !!area?.hasGeo && area.level !== "adm2";

  return (
    <div className="space-y-6">
      <Section title="Combined record" description="harmonized = the combined value; lower/upper = 90 % likely range; source = measured, or which satellite it was converted from.">
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={monthly}>
            <Download /> Monthly (CSV)
          </Button>
          <Button variant="outline" size="sm" onClick={yearly}>
            <Download /> Yearly with likely ranges (CSV)
          </Button>
        </div>
      </Section>
      {hasSub && (
        <Section
          title="Totals by area"
          description="Fire days per sub-area and month, one column per satellite (not converted, like CONAE's 'Totalizar'), and a map layer for GIS with this year compared with normal."
        >
          <div className="flex flex-wrap gap-2">
            <Button variant="outline" size="sm" onClick={totals}>
              <Table /> Monthly totals per sub-area (CSV)
            </Button>
            <Button variant="outline" size="sm" onClick={geojson}>
              <FileJson /> Map layer (GeoJSON)
            </Button>
          </div>
          <Note>Compare periods within one satellite only. The GeoJSON opens in QGIS or ArcGIS (fields: fire_days, normal, change_pct).</Note>
        </Section>
      )}
      {lastDay && <DetectionsDownload lastDay={lastDay} />}
      <Section
        title="Report and images"
        description="A printable report (headline, brief, forecast, map, calendar and charts) to save as PDF, or this view as a picture. The map itself is saved with the camera button above the map."
      >
        <div className="flex flex-wrap gap-2">
          <Button variant="outline" size="sm" onClick={openReport} disabled={own || !area}>
            <FileText /> PDF report
          </Button>
          <Button variant="outline" size="sm" onClick={() => window.dispatchEvent(new Event("burning-calendar:save-view"))}>
            <ImageDown /> Save this view as image
          </Button>
        </div>
        {own && <Note>The report is made for listed areas; open the country, state or district around your shape.</Note>}
      </Section>
    </div>
  );
}
