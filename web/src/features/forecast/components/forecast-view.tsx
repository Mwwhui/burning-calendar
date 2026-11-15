"use client";

import { Area, CartesianGrid, ComposedChart, Line, XAxis, YAxis } from "recharts";

import { Callout, Note, Section } from "@/components/common/section";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { C } from "@/lib/chart-colors";
import { useForecast } from "@/lib/data/queries";
import type { ForecastData, ForecastHorizon } from "@/lib/data/types";
import { formatCompact, formatDay, formatInt } from "@/lib/format";
import { cn } from "@/lib/utils";

function addDays(iso: string, n: number): string {
  const d = new Date(`${iso}T00:00:00Z`);
  d.setUTCDate(d.getUTCDate() + n);
  return d.toISOString().slice(0, 10);
}

function dates(issued: string, h: "h1" | "h4"): string {
  const [a, b] = h === "h1" ? [1, 7] : [8, 28];
  return `${formatDay(addDays(issued, a)).replace(/ \d{4}$/, "")} – ${formatDay(addDays(issued, b))}`;
}

function pct(x: number | null | undefined) {
  return x === null || x === undefined ? "–" : `${Math.round(x * 100)} %`;
}

/** Compact forecast card for the Overview tab. */
export function ForecastCard({ areaId }: { areaId: string }) {
  const { data } = useForecast(areaId);
  if (!data) return null;
  const h = data.horizons.h1;
  if (!h.usable) return null;
  return <HorizonCard h={h} title={`Forecast · next 7 days (${dates(data.issued, "h1")})`} compact />;
}

function HorizonCard({ h, title, compact }: { h: ForecastHorizon; title: string; compact?: boolean }) {
  const up = (h.pAbove ?? 0.5) >= 0.6;
  const down = (h.pAbove ?? 0.5) <= 0.4;
  return (
    <div className={cn("rounded-xl border p-3", compact ? "bg-card/60" : "bg-card")}>
      <div className="text-[11px] text-muted-foreground">{title}</div>
      <div className="mt-0.5 flex flex-wrap items-baseline gap-x-2">
        <span className="text-lg font-semibold tabular-nums">
          {formatInt(h.q10)}–{formatInt(h.q90)} fire days
        </span>
        <span className="text-sm text-muted-foreground">most likely {formatInt(h.q50)}</span>
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-2 text-[11px]">
        <span
          className={cn(
            "rounded-full px-2 py-0.5 font-medium",
            up && "bg-red-500/15 text-red-600 dark:text-red-400",
            down && "bg-sky-500/15 text-sky-700 dark:text-sky-300",
            !up && !down && "bg-muted text-muted-foreground",
          )}
        >
          {pct(h.pAbove)} chance of more than usual
        </span>
        <span className="text-muted-foreground">usual for these dates: about {formatInt(h.usual)}</span>
      </div>
    </div>
  );
}

/** Forecast section: both horizons, how good the model was, and recent forecasts vs reality. */
export function ForecastSection({ areaId }: { areaId: string }) {
  const { data, isLoading } = useForecast(areaId);
  if (isLoading) return <div className="h-40 animate-pulse rounded-xl bg-muted" />;
  if (!data) return null;
  return (
    <Section
      title="Short-range forecast"
      description={`Issued with data to ${formatDay(data.issued)}. A machine-learning model (gradient-boosted trees) trained on 2012–${data.issued.slice(0, 4)} weekly VIIRS fire days of every listed area.`}
    >
      {(["h1", "h4"] as const).map((k) => {
        const h = data.horizons[k];
        const title = `${k === "h1" ? "Next 7 days" : "Weeks 2–4"} · ${dates(data.issued, k)}`;
        return h.usable ? (
          <div key={k} className="space-y-1">
            <HorizonCard h={h} title={title} />
            <Skill h={h} />
          </div>
        ) : (
          <Callout key={k}>
            <b>{title}: no forecast shown.</b> In tests on {data.testYears[0]}–{data.testYears[data.testYears.length - 1]} the
            model was not clearly better than simply assuming{" "}
            {(h.skillPersist ?? 0) <= 0.05 ? "the same as the last weeks" : "a usual amount for the dates"} here.
          </Callout>
        );
      })}
      {data.weather && <WeatherNow w={data.weather} />}
      {data.history && data.history.actual.length > 4 && <History h={data.history} />}
      <Note>
        Inputs, all known on the issue date: fire in the last 1–8 weeks, the usual amount for these dates (earlier years
        only), time of year, the El Niño index, the area&apos;s peat share
        {data.weatherUsed
          ? " and recent weather (rain in the last 7 and 30 days, dry spell, heat, humidity, wind, soil wetness; NASA POWER)"
          : ""}
        . Weather forecasts for the coming days are not used, so sudden rain or dry spells after the issue date are not
        foreseen. Shown only where, tested on years the model had not seen, it beat both
        &ldquo;same as last week&rdquo; and &ldquo;usual for the date&rdquo;.
      </Note>
    </Section>
  );
}

function Skill({ h }: { h: ForecastHorizon }) {
  return (
    <p className="px-1 text-[11px] text-muted-foreground">
      Tested on {formatInt(h.n)} past weeks here: {pct(h.skillPersist)} smaller errors than &ldquo;same as last week&rdquo;,{" "}
      {pct(h.skillClim)} smaller than &ldquo;usual for the date&rdquo;; the real value fell inside the range {pct(h.coverage)} of
      the time; above / below usual called right {pct(h.hit)} of the time.
    </p>
  );
}

function History({ h }: { h: NonNullable<ForecastData["history"]> }) {
  const data = h.targetEnd.map((d, i) => ({
    d,
    actual: h.actual[i],
    q50: h.q50[i],
    band: [h.q10[i] ?? 0, h.q90[i] ?? 0] as [number, number],
    usual: h.usual[i],
  }));
  return (
    <div className="space-y-1 pt-1">
      <h4 className="text-xs font-semibold">Recent weeks: what the model said vs what happened</h4>
      <ChartContainer config={{}} className="aspect-[16/8] w-full">
        <ComposedChart data={data} margin={{ top: 6, right: 6, left: 0, bottom: 0 }}>
          <CartesianGrid vertical={false} strokeDasharray="3 3" />
          <XAxis dataKey="d" tickLine={false} axisLine={false} minTickGap={36} tickFormatter={(v: string) => formatDay(v).replace(/ \d{4}$/, "")} />
          <YAxis tickLine={false} axisLine={false} width={36} tickFormatter={(v) => formatCompact(v)} />
          <ChartTooltip
            content={({ active, payload }) => {
              const p = active && payload?.[0]?.payload;
              return p ? (
                <div className="rounded-md border bg-popover/95 px-2.5 py-1.5 text-xs shadow">
                  <div className="font-medium">Week to {formatDay(p.d)}</div>
                  <div>Happened: {formatInt(p.actual)}</div>
                  <div className="text-muted-foreground">
                    Forecast {formatInt(p.band[0])}–{formatInt(p.band[1])} (most likely {formatInt(p.q50)})
                  </div>
                  <div className="text-muted-foreground">Usual: {formatInt(p.usual)}</div>
                </div>
              ) : null;
            }}
          />
          <Area dataKey="band" stroke="none" fill={C.estimated} fillOpacity={0.3} isAnimationActive={false} />
          <Line dataKey="usual" stroke={C.typical} strokeDasharray="4 3" dot={false} strokeWidth={1.5} isAnimationActive={false} />
          <Line dataKey="q50" stroke={C.estimated} dot={false} strokeWidth={1.5} isAnimationActive={false} />
          <Line dataKey="actual" stroke={C.highlight} dot={{ r: 2 }} strokeWidth={2} isAnimationActive={false} />
        </ComposedChart>
      </ChartContainer>
      <div className="flex flex-wrap gap-x-3 text-[11px] text-muted-foreground">
        <span className="flex items-center gap-1"><span className="inline-block w-3 border-t-2" style={{ borderColor: C.highlight }} /> happened</span>
        <span className="flex items-center gap-1"><span className="inline-block h-2 w-3 rounded-sm" style={{ background: C.estimated, opacity: 0.4 }} /> forecast range (10–90 %)</span>
        <span className="flex items-center gap-1"><span className="inline-block w-3 border-t-2 border-dashed" style={{ borderColor: C.typical }} /> usual</span>
      </div>
      <Note>Each forecast was made by a model trained only on earlier years (backtest), one week ahead.</Note>
    </div>
  );
}

/** The weather behind the forecast: rain vs usual, dry spell, soil wetness. */
function WeatherNow({ w }: { w: NonNullable<ForecastData["weather"]> }) {
  const share = w.rain30OfUsual;
  const dry = share !== null && share < 0.6;
  const wet = share !== null && share > 1.4;
  return (
    <div className="space-y-1 rounded-xl border bg-card/60 p-3 text-sm">
      <div className="text-[11px] text-muted-foreground">Recent weather where it usually burns (NASA POWER, to the issue date)</div>
      <div className="flex flex-wrap gap-x-4 gap-y-1">
        <span>
          Rain, last 30 days: <b className="tabular-nums">{formatInt(w.rain30mm)} mm</b>
          {share !== null && (
            <span className={cn("ml-1 text-xs", dry ? "text-red-600" : wet ? "text-sky-600" : "text-muted-foreground")}>
              ({Math.round(share * 100)} % of usual)
            </span>
          )}
        </span>
        {w.dryDays !== null && (
          <span>
            Dry spell: <b className="tabular-nums">{formatInt(w.dryDays)} day{w.dryDays === 1 ? "" : "s"}</b>
          </span>
        )}
        {w.soilAnom !== null && (
          <span>
            Topsoil: <b>{w.soilAnom < -0.05 ? "drier than usual" : w.soilAnom > 0.05 ? "wetter than usual" : "about usual"}</b>
          </span>
        )}
      </div>
    </div>
  );
}
