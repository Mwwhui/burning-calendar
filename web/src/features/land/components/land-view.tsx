"use client";

import { MapPin, Satellite } from "lucide-react";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, Cell, XAxis, YAxis } from "recharts";

import { Callout, Empty, Note, Section, Stat } from "@/components/common/section";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { useExplorer } from "@/features/explorer/store";
import { latestPhotoDay } from "@/features/map/components/photo-bar";
import { spotColor } from "@/features/map/lib/layers";
import { changeCss } from "@/lib/colors";
import { download, safeName, toCsv } from "@/lib/csv";
import { useLand, useSpots } from "@/lib/data/queries";
import type { AreaMeta, LandData, SpotsData } from "@/lib/data/types";
import { formatCompact, formatInt, formatPct, monthSpan } from "@/lib/format";
import { cn } from "@/lib/utils";

/** Who is responsible for the land that burns: concessions and repeat burn spots. */
export function LandView({ area }: { area: AreaMeta }) {
  const { data: land, isLoading: l1 } = useLand(area.land ? area.id : undefined);
  const { data: spots, isLoading: l2 } = useSpots(area.spots ? area.id : undefined);
  if (l1 || l2) return <div className="h-64 animate-pulse rounded-xl bg-muted" />;
  if (!land && !spots) {
    return <Empty>Land-use views are available for countries, states and districts with fine fire data.</Empty>;
  }
  return (
    <div className="space-y-7">
      {land ? <Concessions land={land} name={area.name} /> : <ConcessionsMissing />}
      {spots && <Spots s={spots} name={area.name} />}
    </div>
  );
}

function ConcessionsMissing() {
  return (
    <Callout>
      No openly licensed concession map covers this area yet. Mapped so far: oil palm concessions in Sarawak (CC BY 4.0).
      Indonesia&apos;s concession maps on Global Forest Watch are view-only, so they cannot be used here.
    </Callout>
  );
}

function Concessions({ land, name }: { land: LandData; name: string }) {
  const setConcession = useExplorer((s) => s.setConcession);
  const picked = useExplorer((s) => s.concession);
  const [sort, setSort] = useState<"this" | "change">("this");
  const data = land.years.map((y, i) => {
    const t = land.total[i] ?? 0;
    const inside = land.inside[i] ?? 0;
    return { year: y, inside, outside: Math.max(0, t - inside), share: t > 0 ? inside / t : 0 };
  });
  const last = data[data.length - 1];
  const full = data.filter((d) => d.year < land.year);
  const typicalShare = full.length ? full.slice(-7).reduce((a, d) => a + d.share, 0) / Math.min(7, full.length) : null;
  const rows = useMemo(
    () =>
      [...land.concessions].sort((a, b) =>
        sort === "this" ? (b.this ?? 0) - (a.this ?? 0) : (b.changePct ?? -Infinity) - (a.changePct ?? -Infinity),
      ),
    [land, sort],
  );
  const span = `${monthSpan(land.throughMonth)} ${land.year}`;
  const burning = land.concessions.filter((c) => (c.this ?? 0) > 0).length;

  return (
    <Section
      title="Fire inside oil palm concessions"
      description={`${land.source.name}: ${land.concessions.length} mapped licences with fire in ${name}.`}
    >
      <div className="grid grid-cols-2 gap-2">
        <Stat
          label={`Share of fire inside, ${land.year} so far`}
          value={last ? `${Math.round(last.share * 100)} %` : "–"}
          sub={typicalShare !== null ? `typical recent year: ${Math.round(typicalShare * 100)} %` : undefined}
        />
        <Stat label={`Licences with fire, ${span}`} value={formatInt(burning)} sub={`of ${land.concessions.length} with fire since 2000`} />
      </div>

      <ChartContainer config={{}} className="aspect-[16/8] w-full">
        <BarChart data={data} margin={{ top: 6, right: 4, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" />
          <XAxis dataKey="year" tickLine={false} axisLine={false} minTickGap={16} />
          <YAxis tickLine={false} axisLine={false} width={40} tickFormatter={(v) => formatCompact(v)} />
          <ChartTooltip
            content={({ active, payload }) => {
              const d = active && payload?.[0]?.payload;
              return d ? (
                <div className="rounded-md border bg-popover/95 px-2.5 py-1.5 text-xs shadow">
                  <div className="font-medium">{d.year}</div>
                  <div>Inside concessions: {formatInt(d.inside)} ({Math.round(d.share * 100)} %)</div>
                  <div className="text-muted-foreground">Elsewhere: {formatInt(d.outside)}</div>
                </div>
              ) : null;
            }}
          />
          <Bar dataKey="inside" stackId="a" fill="#0d9488" isAnimationActive={false} />
          <Bar dataKey="outside" stackId="a" fill="#cbd5e1" radius={[2, 2, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ChartContainer>
      <div className="flex gap-4 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-[#0d9488]" /> inside mapped concessions</span>
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-[#cbd5e1]" /> elsewhere</span>
      </div>

      <div className="flex items-center justify-between gap-2 pt-2">
        <h4 className="text-xs font-semibold">Licences, {span}</h4>
        <div className="flex items-center gap-1 text-[11px]">
          <span className="text-muted-foreground">Sort by</span>
          {(["this", "change"] as const).map((k) => (
            <button
              key={k}
              type="button"
              onClick={() => setSort(k)}
              className={cn("rounded px-1.5 py-0.5", sort === k ? "bg-foreground text-background" : "hover:bg-muted")}
            >
              {k === "this" ? "fire days" : "change"}
            </button>
          ))}
          <button
            type="button"
            className="ml-1 rounded px-1.5 py-0.5 hover:bg-muted"
            onClick={() =>
              download(
                `concessions_${safeName(name)}_${land.year}.csv`,
                toCsv(
                  ["name", "group", "km2", `fire_days_${land.year}_jan_${land.throughMonth}`, "typical_same_months", "change_pct", ...land.years.map((y) => `harmonized_${y}`)],
                  land.concessions.map((c) => [c.name, c.group, c.km2, c.this, c.typical, c.changePct, ...c.fireDays]),
                ),
              )
            }
          >
            CSV
          </button>
        </div>
      </div>
      <ul className="max-h-72 divide-y overflow-y-auto rounded-xl border">
        {rows.slice(0, 60).map((c) => (
          <li key={c.id}>
            <button
              type="button"
              onClick={() => setConcession({ id: c.id, bbox: c.bbox })}
              className={cn(
                "grid w-full grid-cols-[1fr_3.5rem_4rem] items-center gap-2 px-2.5 py-1.5 text-left text-sm hover:bg-muted/60",
                picked?.id === c.id && "bg-teal-500/10",
              )}
            >
              <span className="min-w-0">
                <span className="block truncate">{c.name}</span>
                <span className="block truncate text-[11px] text-muted-foreground">
                  {[c.group, c.km2 ? `${formatInt(c.km2)} km²` : ""].filter(Boolean).join(" · ")}
                </span>
              </span>
              <span className="text-right tabular-nums">{formatInt(c.this)}</span>
              <span
                className="rounded px-1 text-right text-xs tabular-nums"
                style={c.changePct !== null ? { backgroundColor: changeCss(c.changePct), color: Math.abs(c.changePct) > 60 ? "white" : "#111" } : undefined}
              >
                {c.changePct === null ? "–" : formatPct(c.changePct)}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <Note>
        Fire days per licence: NOAA-20 detections in {span}, against the same months of {land.baseYears[0]}–
        {land.baseYears[land.baseYears.length - 1]} (– = too few to compare). Yearly shares: the year&apos;s combined record
        split by where the satellites saw fire. A ~2 km fire cell counts as inside when the mean position of its detections
        is inside the licence. Click a licence to see it on the map.
      </Note>
      <Note>
        Source: {land.source.credit} ({land.source.license}). {land.source.note} A fire inside a licence is not proof of who lit
        it.
      </Note>
    </Section>
  );
}

function Spots({ s, name }: { s: SpotsData; name: string }) {
  const setFocus = useExplorer((st) => st.setFocus);
  const photo = useExplorer((st) => st.photo);
  const setPhoto = useExplorer((st) => st.setPhoto);
  const n = s.lastYear - s.firstYear + 1;
  const many = Math.max(6, Math.round(n / 2));
  const counts = useMemo(() => {
    const idx = s.years.map((_, i) => i);
    const sel = idx.filter((i) => s.years[i] >= many);
    return {
      many: s.histogram.slice(many - 1).reduce((a, b) => a + b, 0),
      thisYear: sel.filter((i) => s.last[i] === s.lastYear).length,
      peat: sel.filter((i) => s.peat[i]).length,
      conc: sel.filter((i) => s.conc[i] >= 0).length,
      sel,
    };
  }, [s, many]);
  const hist = s.histogram.map((v, k) => ({ years: k + 1, cells: v }));
  const top = counts.sel.slice(0, 40);

  return (
    <Section
      title="Repeat burn spots"
      description={`~2 km places in ${name} that a VIIRS satellite saw burning in many of the ${n} years ${s.firstYear}–${s.lastYear}. Burning in most years usually means farmland, plantations or recurring land clearing.`}
    >
      <div className="grid grid-cols-2 gap-2">
        <Stat label={`Burned in ${many}+ of ${n} years`} value={formatInt(counts.many)} sub={`of ${formatInt(s.cellsBurned)} places that ever burned`} />
        <Stat label={`…of which burned in ${s.lastYear}`} value={formatInt(counts.thisYear)} sub={`${formatInt(counts.peat)} on peat · ${formatInt(counts.conc)} in concessions`} />
      </div>
      <ChartContainer config={{}} className="aspect-[16/7] w-full">
        <BarChart data={hist} margin={{ top: 6, right: 4, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" />
          <XAxis dataKey="years" tickLine={false} axisLine={false} />
          <YAxis scale="log" domain={[1, "auto"]} allowDataOverflow tickLine={false} axisLine={false} width={40} tickFormatter={(v) => formatCompact(v)} />
          <ChartTooltip
            content={({ active, payload }) => {
              const d = active && payload?.[0]?.payload;
              return d ? (
                <div className="rounded-md border bg-popover/95 px-2 py-1 text-xs shadow">
                  {formatInt(d.cells)} places burned in {d.years} of {n} years
                </div>
              ) : null;
            }}
          />
          <Bar dataKey="cells" isAnimationActive={false} radius={[2, 2, 0, 0]}>
            {hist.map((h) => (
              <Cell key={h.years} fill={`rgb(${spotColor(Math.max(h.years, 3), n).slice(0, 3).join(",")})`} />
            ))}
          </Bar>
        </BarChart>
      </ChartContainer>
      <Note>Places by number of years with fire (log scale). Turn on &ldquo;Repeat spots&rdquo; above the map to see them.</Note>

      <div className="flex flex-wrap items-center justify-between gap-2 pt-1">
        <h4 className="text-xs font-semibold">Places that burn most often</h4>
        <button
          type="button"
          aria-pressed={!!photo}
          onClick={() => setPhoto(photo ? null : { date: latestPhotoDay(), detail: true })}
          className={cn("inline-flex items-center gap-1 rounded-md border px-2 py-0.5 text-[11px] hover:bg-muted", photo && "border-sky-500 text-sky-700 dark:text-sky-300")}
        >
          <Satellite className="size-3" /> {photo ? "Satellite photo on" : "See places on a satellite photo"}
        </button>
      </div>
      <ul className="max-h-72 divide-y overflow-y-auto rounded-xl border">
        {top.map((i, k) => (
          <li key={i}>
            <button
              type="button"
              onClick={() => setFocus({ lon: s.lon[i], lat: s.lat[i] })}
              className="grid w-full grid-cols-[1.4rem_1fr_auto] items-center gap-2 px-2.5 py-1.5 text-left text-sm hover:bg-muted/60"
            >
              <span className="text-xs text-muted-foreground tabular-nums">{k + 1}</span>
              <span className="min-w-0">
                <span className="block truncate tabular-nums">
                  {s.lat[i].toFixed(3)}°N, {s.lon[i].toFixed(3)}°E
                </span>
                <span className="flex flex-wrap gap-1 text-[11px] text-muted-foreground">
                  last {s.last[i]}
                  {s.peat[i] ? <span className="rounded bg-amber-700/15 px-1 text-amber-800 dark:text-amber-300">peat</span> : null}
                  {s.conc[i] >= 0 ? (
                    <span className="truncate rounded bg-teal-600/15 px-1 text-teal-800 dark:text-teal-300">{s.concNames[String(s.conc[i])] ?? "concession"}</span>
                  ) : null}
                </span>
              </span>
              <span className="flex items-center gap-1.5">
                <YearDots mask={s.mask[i]} n={n} />
                <span className="w-9 text-right text-xs font-medium tabular-nums">
                  {s.years[i]}/{n}
                </span>
                <MapPin className="size-3.5 text-muted-foreground" />
              </span>
            </button>
          </li>
        ))}
      </ul>
      <Note>
        Counted from {s.firstYear} so every year is seen by the same kind of sensor (VIIRS: Suomi NPP to 2018, NOAA-20 from
        2019); a place &ldquo;burned&rdquo; in a year when at least one fire was detected in it. Clouds and smoke hide some
        fires, so counts are a lower bound.{s.truncated ? ` Only the ${formatInt(s.lon.length)} most frequent places are listed.` : ""}
      </Note>
    </Section>
  );
}

/** One tiny square per year, filled when the place burned. */
function YearDots({ mask, n }: { mask: number; n: number }) {
  return (
    <span className="hidden gap-[1px] @[380px]:flex" aria-hidden>
      {Array.from({ length: n }, (_, k) => (
        <span key={k} className={cn("h-2.5 w-[3px] rounded-[1px]", (mask >> k) & 1 ? "bg-fuchsia-600" : "bg-muted")} />
      ))}
    </span>
  );
}
