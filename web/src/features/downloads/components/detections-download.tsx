"use client";

import { Download, Loader2, Search } from "lucide-react";
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";

import { Callout, Note, Section } from "@/components/common/section";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useCurrentArea } from "@/features/explorer/hooks/use-area";
import { useExplorer } from "@/features/explorer/store";
import { ancestry, countryOf } from "@/lib/area";
import { SAT_NAME } from "@/lib/chart-colors";
import { download, safeName, toCsv } from "@/lib/csv";
import {
  DETECTION_COLUMNS,
  DETECTIONS_BASE,
  filesFor,
  MAX_ROWS,
  searchDetections,
  type DetectionQuery,
  type DetectionResult,
  type DetectionsIndex,
} from "@/lib/detections";
import { isoDay, parseDay } from "@/lib/analytics/window";
import { formatDay, formatInt } from "@/lib/format";

const SATS = ["", "NOAA20", "NOAA21", "SNPP", "Aqua", "Terra"];

/** "A downloadable CSV of hotspots detected in a search" (challenge brief): any area and dates. */
export function DetectionsDownload({ lastDay }: { lastDay: string }) {
  const { lookup, area, id } = useCurrentArea();
  const ownArea = useExplorer((s) => s.ownArea);
  const dates = useExplorer((s) => s.dates);
  const { data: index } = useQuery({
    queryKey: ["detections-index"],
    queryFn: async () => {
      const r = await fetch(`${DETECTIONS_BASE}/index.json`);
      return r.ok ? ((await r.json()) as DetectionsIndex) : null;
    },
    staleTime: Infinity,
    retry: false,
  });
  const [d0, setD0] = useState(dates?.[0] ?? isoDay(parseDay(lastDay) - 6 * 86_400_000));
  const [d1, setD1] = useState(dates?.[1] ?? lastDay);
  const [sat, setSat] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [result, setResult] = useState<DetectionResult | null>(null);

  if (!lookup || !area) return null;

  // which countries and filters the current area means
  const trail = ancestry(lookup, id);
  const country = countryOf(lookup, ownArea?.countryId ?? id);
  const countries =
    country !== undefined
      ? [country]
      : lookup.get(id)?.level === "group" || id === ""
        ? collectCountries(lookup, id)
        : [];
  const adm1 = !ownArea && (area.level === "adm1" || area.level === "adm2") ? trail.find((a) => a.level === "adm1")?.name : null;
  const adm2 = !ownArea && area.level === "adm2" ? area.name : null;
  const days = (parseDay(d1) - parseDay(d0)) / 86_400_000 + 1;
  const maxDays = countries.length > 1 ? 31 : 366;
  const query: DetectionQuery = { countries, start: d0, end: d1, adm1, adm2, satellite: sat || null, ring: ownArea?.ring ?? null };
  const nFiles = index ? filesFor(index, query).length : 0;

  async function run() {
    if (!index) return;
    setBusy(true);
    setError(null);
    setResult(null);
    try {
      setResult(await searchDetections(index, query));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function save() {
    if (!result) return;
    const name = safeName(ownArea ? "my_area" : area!.name || "asia");
    download(
      `detections_${name}_${d0}_${d1}.csv`,
      toCsv([...DETECTION_COLUMNS], result.rows.map((r) => DETECTION_COLUMNS.map((c) => r[c]))),
    );
  }

  return (
    <Section
      title="Fire detections (hotspots CSV)"
      description="Every satellite detection in this area and these dates, as recorded by NASA FIRMS after cleaning (confidence, gas-flare mask). Not converted: each row names its satellite."
    >
      {index === null ? (
        <Callout>The detection files are not exported yet (python scripts/export_points.py).</Callout>
      ) : (
        <>
          <div className="flex flex-wrap items-end gap-2">
            <label className="space-y-1 text-xs text-muted-foreground">
              From
              <Input type="date" value={d0} max={d1} onChange={(e) => e.target.value && setD0(e.target.value)} className="h-8 w-[145px]" />
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              To
              <Input type="date" value={d1} min={d0} max={lastDay} onChange={(e) => e.target.value && setD1(e.target.value)} className="h-8 w-[145px]" />
            </label>
            <label className="space-y-1 text-xs text-muted-foreground">
              Satellite
              <select value={sat} onChange={(e) => setSat(e.target.value)} className="block h-8 rounded-md border bg-background px-2 text-sm text-foreground">
                {SATS.map((s) => (
                  <option key={s} value={s}>
                    {s ? (SAT_NAME[s] ?? s) : "All satellites"}
                  </option>
                ))}
              </select>
            </label>
            <Button size="sm" onClick={run} disabled={busy || !index || !countries.length || days < 1 || days > maxDays}>
              {busy ? <Loader2 className="animate-spin" /> : <Search />} Find detections
            </Button>
          </div>
          {days > maxDays && (
            <Note>
              Choose at most {maxDays} days {countries.length > 1 ? "for a region of several countries (open one country for longer periods)" : ""}.
            </Note>
          )}
          {!countries.length && <Note>Open a country, state or district (or draw an area) to search its detections.</Note>}
          {error && <Callout tone="warn">Search failed: {error}</Callout>}
          {busy && <Note>Reading {nFiles} file{nFiles === 1 ? "" : "s"} in your browser…</Note>}
          {result && (
            <div className="space-y-2 rounded-xl border bg-card/60 p-3">
              <div className="flex flex-wrap items-baseline justify-between gap-2">
                <span className="text-sm">
                  <b className="tabular-nums">{formatInt(result.rows.length)}</b> detections, {formatDay(d0)} – {formatDay(d1)}
                  {result.truncated && ` (first ${formatInt(MAX_ROWS)} only: choose fewer days or a smaller area)`}
                </span>
                <Button size="sm" variant="outline" onClick={save} disabled={!result.rows.length}>
                  <Download /> Download CSV
                </Button>
              </div>
              {Object.keys(result.bySatellite).length > 0 && (
                <div className="flex flex-wrap gap-x-3 text-[11px] text-muted-foreground">
                  {Object.entries(result.bySatellite).map(([s, n]) => (
                    <span key={s}>
                      {SAT_NAME[s] ?? s}: <b className="text-foreground tabular-nums">{formatInt(n)}</b>
                    </span>
                  ))}
                </div>
              )}
            </div>
          )}
          <Note>
            Columns: latitude, longitude, acq_date and acq_time (UTC, as in FIRMS), solar_date (local date used for counting),
            satellite, confidence, frp (fire radiative power, MW), daynight, adm1, adm2. Satellites see different amounts of fire,
            so compare periods with the combined record, not with raw counts. Files are read in your browser; nothing is sent
            anywhere.
          </Note>
        </>
      )}
    </Section>
  );
}

/** Countries under a region (or all of Asia), as lower-case ISO3 ids. */
function collectCountries(lookup: NonNullable<ReturnType<typeof useCurrentArea>["lookup"]>, id: string): string[] {
  const out: string[] = [];
  const walk = (x: string) => {
    const a = lookup.get(x);
    if (!a) return;
    if (a.level === "country") out.push(a.id);
    else a.children.forEach(walk);
  };
  walk(id);
  return out;
}
