"use client";

import { Flame, MapPin, Pause, Play, Satellite } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { CartesianGrid, Line, LineChart, ReferenceLine, XAxis, YAxis } from "recharts";

import { Callout, Empty, Note, Section, Stat } from "@/components/common/section";
import { ChartContainer } from "@/components/ui/chart";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useExplorer } from "@/features/explorer/store";
import { latestPhotoDay } from "@/features/map/components/photo-bar";
import { pointInRing, type Ring } from "@/lib/analytics/own-area";
import { C } from "@/lib/chart-colors";
import { useEventDots, useEvents } from "@/lib/data/queries";
import type { FireEvent, GrowthSummary } from "@/lib/data/types";
import { formatCompact, formatDay } from "@/lib/format";
import { shiftDay } from "@/lib/gibs";
import { cn } from "@/lib/utils";

import { dayColor, decodeDots, dotDate, seenBy } from "../lib/dots";

type ListKey = "active" | "thisYear" | "record";

function km2(v: number): string {
  return v < 10 ? `${v.toFixed(1)} km²` : `${Math.round(v).toLocaleString("en")} km²`;
}

function when(e: FireEvent): string {
  return e.start === e.end ? formatDay(e.start) : `${formatDay(e.start).replace(/ \d{4}$/, "")} – ${formatDay(e.end)}`;
}

/** Fire events (one fire followed day to day), NOAA-20 since April 2018 (app.py "events" tab). */
export function EventsView({ eventsId, ring }: { eventsId: string | undefined; ring?: Ring }) {
  const { data, isLoading } = useEvents(eventsId);
  const event = useExplorer((s) => s.event);
  const setEvent = useExplorer((s) => s.setEvent);
  const [list, setList] = useState<ListKey | null>(null);

  const byId = useMemo(() => new Map((data?.events ?? []).map((e) => [e.id, e])), [data]);
  const inArea = (e: FireEvent) => !ring || pointInRing(e.lon, e.lat, ring);

  if (!eventsId) return <Empty>No fire events recorded in this area since April 2018.</Empty>;
  if (isLoading) return <div className="h-64 animate-pulse rounded-xl bg-muted" />;
  if (!data) return <Empty>No fire events recorded in this area since April 2018.</Empty>;

  const current: ListKey = list ?? (data.nActive > 0 ? "active" : "thisYear");
  const items = data.lists[current].map((i) => byId.get(i)!).filter((e) => e && inArea(e));
  const sel = event && byId.has(event.id) ? event : null;

  return (
    <div className="space-y-5">
      <p className="text-xs leading-relaxed text-muted-foreground">
        A <b className="text-foreground">fire event</b> is one fire followed from day to day: detections in touching ~1 km
        squares, at most 5 days apart, belong to the same event (as in NASA&apos;s Fire Events Data Suite). Only NOAA-20 is
        used, so every event since April 2018 is measured the same way.
        {ring && " Drawn area: events whose centre lies inside it (from this country's top lists)."}
      </p>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <ToggleGroup size="sm" variant="outline" spacing={0} value={[current]} onValueChange={(v) => v[0] && setList(v[0] as ListKey)}>
          <ToggleGroupItem value="active" className="px-2.5">Burning now</ToggleGroupItem>
          <ToggleGroupItem value="thisYear" className="px-2.5">Biggest this year</ToggleGroupItem>
          <ToggleGroupItem value="record" className="px-2.5">On record</ToggleGroupItem>
        </ToggleGroup>
        <span className="text-[11px] text-muted-foreground">
          {data.n.toLocaleString("en")} events since {formatDay(data.first).replace(/^\d+ /, "")}; {data.nActive} burning in the 5 days to {formatDay(data.end)}
        </span>
      </div>

      {items.length === 0 ? (
        <Callout>
          {current === "active" ? "No fires burning in the last 5 days here. Try 'Biggest this year'." : "No events in this list."}
        </Callout>
      ) : (
        <ul className="max-h-64 divide-y overflow-y-auto rounded-xl border">
          {items.slice(0, 50).map((e, i) => (
            <li key={e.id}>
              <button
                type="button"
                onClick={() => setEvent(sel?.id === e.id ? null : e)}
                className={cn(
                  "grid w-full grid-cols-[1.5rem_1fr_auto] items-center gap-2 px-2.5 py-2 text-left text-sm hover:bg-muted/60",
                  sel?.id === e.id && "bg-orange-500/10",
                )}
              >
                <span className="text-xs text-muted-foreground tabular-nums">{i + 1}</span>
                <span className="min-w-0">
                  <span className="block truncate">{e.where}</span>
                  <span className="block text-[11px] text-muted-foreground">{when(e)} · {e.days} days</span>
                </span>
                <span className="text-right font-medium tabular-nums">{km2(e.km2)}</span>
              </button>
            </li>
          ))}
        </ul>
      )}

      {sel ? (
        <EventCard e={sel} lastDay={data.end} curve={data.sizeCurve} growth={data.growth ?? null} />
      ) : (
        <Note>
          <MapPin className="mr-1 inline size-3" />
          Pick a fire to see it on the map and how it compares with earlier fires.
        </Note>
      )}
      <Note>
        Limits: fires burning side by side (e.g. many farm fires) merge into one event; a fire seen only between clouds can
        split. Smouldering peat under smoke may be missed.
      </Note>
    </div>
  );
}

function EventCard({ e, lastDay, curve, growth }: { e: FireEvent; lastDay: string; curve: [number, number][]; growth: GrowthSummary | null }) {
  const recent = Date.parse(e.end) > Date.parse(lastDay) - 5 * 86_400_000;
  const c = e.cmp;
  return (
    <Section title={<span className="flex items-center gap-1.5"><Flame className="size-4 text-orange-500" /> {e.where}, {when(e)}</span>}>
      <div className="grid grid-cols-2 gap-2">
        <Stat label="Area with fire" value={km2(e.km2)} sub="upper bound of burnt area" />
        <Stat label="Duration" value={`${e.days} days${recent ? " so far" : ""}`} />
        <Stat label="Strongest fire seen" value={e.frpMax === null ? "–" : `${Math.round(e.frpMax).toLocaleString("en")} MW`} sub="fire radiative power" />
        <Stat label="On mapped peat" value={e.peat === null ? "–" : `${Math.round(e.peat * 100)} %`} />
      </div>
      <Spread e={e} />
      <SeeFromSpace e={e} />
      <GrowthOutlook e={e} g={growth} recent={recent} />
      {e.km2 >= 1000 && (
        <Callout tone="warn">
          Fires this large and long are usually <b>many fires burning side by side</b> (farm and forest-edge burning across
          a landscape) that touch each other, not one spreading fire. Read the size as &ldquo;area of a burning
          landscape&rdquo;.
        </Callout>
      )}
      {c.n > 0 && (
        <p className="text-sm">
          {c.biggerBefore === null ? (
            <>
              <b>The biggest of all {c.n.toLocaleString("en")} earlier fires</b> recorded in this area.
            </>
          ) : (
            <>
              <b>
                Bigger than {c.shareSmaller !== null && c.shareSmaller > 0.99 && c.shareSmaller < 1 ? "more than 99 %" : `${Math.round((c.shareSmaller ?? 0) * 100)} %`}
              </b>{" "}
              of the {c.n.toLocaleString("en")} earlier fires here; the last bigger one was <b>{km2(c.biggerBefore.km2)}</b> in{" "}
              {formatDay(c.biggerBefore.start).replace(/^\d+ /, "")} ({c.biggerBefore.where}).
            </>
          )}
        </p>
      )}
      {curve.length > 4 && (
        <ChartContainer config={{}} className="aspect-[16/8] w-full">
          <LineChart data={curve.map(([r, v]) => ({ r, v }))} margin={{ top: 8, right: 8, left: 0, bottom: 0 }}>
            <CartesianGrid strokeDasharray="3 3" />
            <XAxis dataKey="r" type="number" scale="log" domain={["dataMin", "dataMax"]} tickLine={false} axisLine={false} tickFormatter={(v) => formatCompact(v)} />
            <YAxis dataKey="v" type="number" scale="log" domain={["auto", "auto"]} tickLine={false} axisLine={false} width={40} tickFormatter={(v) => formatCompact(v)} />
            <Line dataKey="v" stroke={C.neutral} dot={false} strokeWidth={1.5} isAnimationActive={false} />
            <ReferenceLine y={e.km2} stroke={C.highlight} strokeWidth={2} label={{ value: `this fire: ${km2(e.km2)}`, position: "insideTopRight", fontSize: 10, fill: C.highlight }} />
          </LineChart>
        </ChartContainer>
      )}
      <Note>All fires here, biggest first (rank, log scale), with this one marked.</Note>
    </Section>
  );
}

/** Chance a recent fire keeps burning / grows, from the fire-growth model, when it was useful in tests. */
function GrowthOutlook({ e, g, recent }: { e: FireEvent; g: GrowthSummary | null; recent: boolean }) {
  if (!g || !recent || (e.pLong === undefined && e.pBig === undefined)) return null;
  const rows: { label: string; p: number | null | undefined; t?: GrowthSummary["targets"]["long"] }[] = [
    { label: `keeps burning ${g.longDays} days or more`, p: e.pLong, t: g.targets.long },
    { label: `ends up ${g.bigKm2} km² or more`, p: e.pBig, t: g.targets.big },
  ];
  const shown = rows.filter((r) => r.t?.usable && r.p !== null && r.p !== undefined);
  const hidden = rows.filter((r) => !r.t?.usable);
  if (!shown.length && !hidden.length) return null;
  return (
    <div className="space-y-1.5 rounded-xl border bg-card/60 p-3 text-sm">
      <div className="text-[11px] text-muted-foreground">Outlook for this fire (from its first 3 days)</div>
      {shown.map((r) => (
        <div key={r.label} className="flex items-baseline justify-between gap-2">
          <span>Chance it {r.label}</span>
          <span className="font-semibold tabular-nums">{Math.round((r.p ?? 0) * 100)} %</span>
        </div>
      ))}
      {shown.map((r) => (
        <p key={`${r.label}-n`} className="text-[11px] leading-relaxed text-muted-foreground">
          Usually {Math.round((r.t?.base_rate ?? 0) * 100)} % of fires do. Tested on {g.testYears[0]}–{g.testYears[g.testYears.length - 1]}: of the
          1 % of fires the model rated highest, {Math.round((r.t?.p_top1pct_precision ?? 0) * 100)} % did (vs{" "}
          {Math.round((r.t?.baseline_top1pct_precision ?? 0) * 100)} % when ranking by size at day 3).
        </p>
      ))}
      {hidden.map((r) => (
        <p key={`${r.label}-h`} className="text-[11px] text-muted-foreground">
          No estimate for whether it {r.label}: in tests the model was no better than judging by the fire&apos;s size at day 3.
        </p>
      ))}
    </div>
  );
}

/** Before / after satellite photos of the fire (NASA GIBS true colour). */
function SeeFromSpace({ e }: { e: FireEvent }) {
  const setPhoto = useExplorer((s) => s.setPhoto);
  const max = latestPhotoDay();
  const before = shiftDay(e.start, -1);
  const after = shiftDay(e.end, 1) > max ? max : shiftDay(e.end, 1);
  return (
    <button
      type="button"
      onClick={() =>
        setPhoto({ date: after, detail: true, pair: [before, after], fire: { lon: e.lon, lat: e.lat, start: e.start, end: e.end } })
      }
      className="inline-flex items-center gap-1.5 rounded-md border px-2.5 py-1 text-xs hover:bg-muted"
    >
      <Satellite className="size-3.5 text-sky-600" /> See this fire from space (before / after)
    </button>
  );
}

/** The fire's own squares on the map, and a slider to watch it spread day by day. */
function Spread({ e }: { e: FireEvent }) {
  const { data: raw, isLoading, isError } = useEventDots(e.id);
  const dots = useMemo(() => (raw ? decodeDots(raw) : undefined), [raw]);
  const day = useExplorer((s) => s.eventDay);
  const setDay = useExplorer((s) => s.setEventDay);
  const [playing, setPlaying] = useState(false);

  useEffect(() => {
    if (!playing || !dots) return;
    const step = Math.max(1, Math.round(dots.last / 60));
    const t = setInterval(() => {
      const cur = useExplorer.getState().eventDay;
      const next = cur === null || cur >= dots.last ? 0 : Math.min(dots.last, cur + step);
      setDay(next);
      if (next >= dots.last) setPlaying(false);
    }, 180);
    return () => clearInterval(t);
  }, [playing, dots, setDay]);

  if (isLoading) return <div className="h-14 animate-pulse rounded-xl bg-muted" />;
  if (isError || !dots) return <Note>The squares of this fire are not in this export.</Note>;
  const css = (d: number) => `rgb(${dayColor(d, dots.last).slice(0, 3).join(",")})`;
  const today = day === null ? null : dots.perDay[day] ?? 0;

  return (
    <div className="space-y-1.5 rounded-xl border bg-card/60 p-3 text-xs">
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">Where it burned, day by day</span>
        <span className="text-muted-foreground tabular-nums">{dots.n.toLocaleString("en")} fire days in {dots.perDay.filter((c) => c > 0).length} days with detections</span>
      </div>
      {dots.last > 0 && (
        <div className="flex items-center gap-2">
          <button
            type="button"
            aria-label={playing ? "Pause" : "Play the fire's spread"}
            onClick={() => {
              if (!playing && (day === null || day >= dots.last)) setDay(0);
              setPlaying(!playing);
            }}
            className="inline-flex size-7 shrink-0 items-center justify-center rounded-md border hover:bg-muted"
          >
            {playing ? <Pause className="size-3.5" /> : <Play className="size-3.5" />}
          </button>
          <input
            type="range"
            aria-label="Day of the fire"
            min={0}
            max={dots.last}
            value={day ?? dots.last}
            onChange={(ev) => {
              setPlaying(false);
              setDay(Number(ev.target.value));
            }}
            className="min-w-0 flex-1 accent-orange-600"
          />
          <button type="button" disabled={day === null} onClick={() => { setPlaying(false); setDay(null); }} className="rounded-md border px-2 py-1 hover:bg-muted disabled:opacity-40">
            All
          </button>
        </div>
      )}
      <p className="tabular-nums">
        {day === null ? (
          <>Whole fire, {formatDay(e.start)} – {formatDay(e.end)}</>
        ) : (
          <>
            <b>Day {day + 1}</b> of {dots.last + 1}, {formatDay(dotDate(dots, day))}: {today ? `${today.toLocaleString("en")} squares burning` : "nothing seen (cloud, smoke or a pause)"}
            {" · "}
            {seenBy(dots, day).toLocaleString("en")} so far
          </>
        )}
      </p>
      <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
        <span>first day</span>
        <span className="h-2 flex-1 rounded-sm" style={{ background: `linear-gradient(to right, ${css(0)}, ${css(dots.last / 2)}, ${css(dots.last)})` }} />
        <span>last day</span>
      </div>
      <p className="text-[11px] leading-snug text-muted-foreground">
        Each square is ~1 km where NOAA-20 saw fire; the dark-edged squares burned on the chosen day. Hover a square for its date and
        strength.
      </p>
    </div>
  );
}
