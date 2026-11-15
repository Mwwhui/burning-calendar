"use client";

import { ExternalLink } from "lucide-react";
import { useMemo, useState } from "react";
import { Bar, BarChart, CartesianGrid, XAxis, YAxis } from "recharts";

import { Note, Section } from "@/components/common/section";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { useAsmc } from "@/lib/data/queries";
import type { GfedCheck, OfficialCheck } from "@/lib/data/types";
import { formatPeriod } from "@/lib/format";

function pctStep(x: number | null) {
  if (x === null) return "–";
  return `${x > 0 ? "+" : "−"}${Math.abs(Math.round(x * 100))} %`;
}

function PairBars({ years, a, b, aLabel, bLabel }: { years: number[]; a: (number | null)[]; b: (number | null)[]; aLabel: string; bLabel: string }) {
  const ma = Math.max(1, ...a.map((v) => v ?? 0));
  const mb = Math.max(1, ...b.map((v) => v ?? 0));
  const data = years.map((y, i) => ({ year: y, a: (a[i] ?? 0) / ma, b: (b[i] ?? 0) / mb }));
  return (
    <>
      <ChartContainer config={{ a: { label: aLabel, color: "#c81d25" }, b: { label: bLabel, color: "#71717a" } }} className="aspect-[16/8] w-full">
        <BarChart data={data} margin={{ top: 6, right: 4, left: 0, bottom: 0 }} barGap={1}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" />
          <XAxis dataKey="year" tickLine={false} axisLine={false} minTickGap={14} />
          <YAxis tickLine={false} axisLine={false} width={42} domain={[0, 1]} tickFormatter={(v) => `${Math.round(v * 100)}%`} />
          <ChartTooltip
            content={({ active, payload }) => {
              const d = active && payload?.[0]?.payload;
              return d ? (
                <div className="rounded-md border bg-popover/95 px-2.5 py-1.5 text-xs shadow">
                  <div className="font-medium">{d.year}</div>
                  <div>{aLabel}: {Math.round(d.a * 100)} % of its biggest year</div>
                  <div>{bLabel}: {Math.round(d.b * 100)} % of its biggest year</div>
                </div>
              ) : null;
            }}
          />
          <Bar dataKey="a" fill="var(--color-a)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
          <Bar dataKey="b" fill="var(--color-b)" radius={[2, 2, 0, 0]} isAnimationActive={false} />
        </BarChart>
      </ChartContainer>
      <div className="flex gap-4 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-[#c81d25]" /> {aLabel}</span>
        <span className="flex items-center gap-1.5"><span className="size-2.5 rounded-sm bg-[#71717a]" /> {bLabel}</span>
      </div>
    </>
  );
}

/** Independent checks: official figures, GFED5 burned area, ASMC reviews (app.py "checks" tab). */
export function ChecksView({ official, gfed, asia = true }: { official: OfficialCheck | null | undefined; gfed: GfedCheck | null | undefined; asia?: boolean }) {
  const { data: asmc } = useAsmc();
  const months = useMemo(() => (asmc ? Object.keys(asmc).sort().reverse() : []), [asmc]);
  const [month, setMonth] = useState<string | undefined>();
  const m = month ?? months[0];

  return (
    <div className="space-y-6">
      <p className="text-xs leading-relaxed text-muted-foreground">
        Do other sources show the same good and bad years? A satellite record that only reflected changes of satellites
        would fail these checks.
      </p>

      <Section title="Official figures">
        {official ? (
          <>
            <p className="text-sm">
              Indonesia&apos;s official burned area (SiPongi) against the combined record, {official.years[0]}–
              {official.years[official.years.length - 1]}: rank correlation <b>{official.spearman?.toFixed(2)}</b> (1 = same
              order of years){official.sameTop3 ? ", and both put the same three years at the top." : "."}
            </p>
            <PairBars years={official.years} a={official.fireDays} b={official.official} aLabel="Satellite record" bLabel="Official burned area" />
            <Note>Sources: {official.sources.join("; ")}. Burned area and fire days measure different things, so only the ups and downs are compared.</Note>
          </>
        ) : (
          <Note>
            An open, year-by-year official series was found only for Indonesia (SiPongi burned area); open Indonesia to see
            it. Malaysia&apos;s fire department reports open-burning cases with changing periods, which cannot be compared
            year to year.
          </Note>
        )}
      </Section>

      <Section title="Burned area from another method (GFED5)">
        {gfed ? (
          <>
            <p className="text-sm leading-relaxed">
              GFED5 maps burnt ground (not hot spots) from MODIS images, {gfed.first}–{gfed.last}. Agreement with the combined
              record: months <b>{gfed.rMonthly?.toFixed(2)}</b>, ups and downs after removing the usual season{" "}
              <b>{gfed.rAnomaly?.toFixed(2)}</b>, order of years <b>{gfed.rYearlyRank?.toFixed(2)}</b> (1 = perfect). Biggest
              years: satellite record {gfed.top3Fire.join(", ")}; GFED5 {gfed.top3Burned.join(", ")}.
            </p>
            <PairBars years={gfed.years} a={gfed.fireDays} b={gfed.burnedKm2} aLabel="Satellite record" bLabel="GFED5 burned area" />
            {gfed.step2012 !== null && gfed.naiveStep2012 !== null && (
              <p className="text-sm">
                <b>No jump where the satellites change.</b> Compared with GFED5, the combined record changes by{" "}
                <b>{pctStep(gfed.step2012)}</b> in 2012 (VIIRS starts) and {pctStep(gfed.step2018)} in 2018 (NOAA-20 starts).
                Joining the raw satellites instead would jump by <b>{pctStep(gfed.naiveStep2012)}</b> in 2012.
              </p>
            )}
            <Note>GFED5: Chen et al. 2023, AGU Advances (CC BY 4.0), 0.25° grid. GFED5 also uses MODIS, so it is a different method, not a fully separate satellite.</Note>
          </>
        ) : (
          <Note>Available for Asia, regions, countries and provinces with GFED5 data; not for districts or drawn areas.</Note>
        )}
      </Section>

      {asia && (
      <Section title="ASEAN haze reviews (ASMC)" description="Monthly reviews of hotspots, smoke and weather, in words and maps (from mid-2018).">
        {months.length > 0 ? (
          <>
            <select
              value={m}
              onChange={(e) => setMonth(e.target.value)}
              className="h-8 rounded-md border bg-background px-2 text-sm"
              aria-label="Month"
            >
              {months.map((x) => (
                <option key={x} value={x}>
                  {formatPeriod(x)}
                </option>
              ))}
            </select>
            <div className="flex flex-wrap gap-1.5">
              {(asmc?.[m!] ?? []).map(([t, u]) => (
                <a key={u} href={u} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 rounded-md border px-2 py-1 text-xs hover:bg-muted">
                  {t.replace("Review of ", "").replace(" Situation", "")} <ExternalLink className="size-3" />
                </a>
              ))}
            </div>
          </>
        ) : (
          <a href="https://asmc.asean.org/category/haze-review/" target="_blank" rel="noreferrer" className="text-sm underline">
            ASMC haze reviews
          </a>
        )}
      </Section>
      )}
    </div>
  );
}
