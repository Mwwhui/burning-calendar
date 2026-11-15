"use client";

import { Bar, BarChart, CartesianGrid, Cell, LabelList, ReferenceLine, Scatter, ScatterChart, XAxis, YAxis } from "recharts";

import { Callout, Empty, Note, Section } from "@/components/common/section";
import { ChartContainer, ChartTooltip } from "@/components/ui/chart";
import { C } from "@/lib/chart-colors";
import type { Outlook } from "@/lib/data/types";
import { formatCompact, formatInt, formatPeriod, MONTHS_LONG } from "@/lib/format";

function pct(x: number | undefined | null) {
  return x === undefined || x === null ? "–" : `${Math.round(x * 100)} %`;
}

/** Next fire season vs the El Niño index (app.py "outlook" tab). */
export function OutlookView({ o, unit }: { o: Outlook | null | undefined; unit: string }) {
  if (!o) return <Empty>The outlook needs the El Niño index; not available for this area.</Empty>;
  const season = `${MONTHS_LONG[o.months[0] - 1]}–${MONTHS_LONG[o.months[o.months.length - 1] - 1]}`;
  const phase = o.oni === null ? "" : o.oni >= 0.5 ? "El Niño" : o.oni <= -0.5 ? "La Niña" : "neutral";
  const sk = o.skill;
  return (
    <div className="space-y-5">
      <p className="text-sm leading-relaxed">
        <b>Main fire season here: {season}</b> ({pct(o.share)} of a year&apos;s fire on average). Next season starts{" "}
        <b>{formatPeriod(o.seasonStart)}</b>. Latest El Niño index (ONI, {formatPeriod(o.oniMonth)}):{" "}
        <b>
          {o.oni !== null && o.oni > 0 ? "+" : ""}
          {o.oni?.toFixed(1)}
        </b>{" "}
        ({phase}).
      </p>

      {sk.useful && o.p_above !== undefined ? (
        <>
          <Section title={<>Chance of more fire than usual: {pct(o.p_above)}</>}>
            <ChartContainer config={{}} className="aspect-[16/8] w-full">
              <BarChart
                data={[
                  { k: "Less than usual", v: (o.p_below ?? 0) * 100, c: C.less },
                  { k: "Usual", v: (o.p_normal ?? 0) * 100, c: C.neutral },
                  { k: "More than usual", v: (o.p_above ?? 0) * 100, c: C.more },
                ]}
                margin={{ top: 18, right: 4, left: 0, bottom: 0 }}
              >
                <CartesianGrid vertical={false} strokeDasharray="3 3" />
                <XAxis dataKey="k" tickLine={false} axisLine={false} />
                <YAxis domain={[0, 100]} tickLine={false} axisLine={false} width={34} tickFormatter={(v) => `${v}%`} />
                <ReferenceLine y={33.3} stroke={C.typical} strokeDasharray="3 3" />
                <Bar dataKey="v" radius={[3, 3, 0, 0]} isAnimationActive={false}>
                  {[C.less, C.neutral, C.more].map((c) => (
                    <Cell key={c} fill={c} />
                  ))}
                  <LabelList dataKey="v" position="top" formatter={(v) => `${Math.round(Number(v))}%`} className="fill-foreground text-[11px]" />
                </Bar>
              </BarChart>
            </ChartContainer>
            <Note>Dotted line: 33 % = no information (each third equally likely).</Note>
          </Section>
          <p className="text-sm">
            &ldquo;Usual&rdquo; = the middle third of past seasons:{" "}
            <b>
              {formatInt(o.normal_low)}–{formatInt(o.normal_high)} {unit}
            </b>
            . Most likely total: about <b>{formatInt(o.expected)}</b>.
          </p>
          <Callout>
            <b>How good is this?</b> Tested on {sk.n} past seasons, each predicted without its own year: right third{" "}
            {sk.hits} times out of {sk.n} (chance alone: about {Math.round(sk.n / 3)}); correlation {sk.r?.toFixed(2)};{" "}
            {pct(sk.msss)} smaller errors than always guessing an average year. Chances are capped at 5–90 %.
            {o.pastExtremes < 4 &&
              ` Only ${o.pastExtremes} past seasons had an El Niño index this far from zero, so this outlook leans on few examples.`}
          </Callout>
          {o.seasons && (
            <Section title="Past seasons against the El Niño index" description={`El Niño index ${o.lead} months before the season vs ${unit} in ${season} (log scale).`}>
              <ChartContainer config={{}} className="aspect-[16/10] w-full">
                <ScatterChart margin={{ top: 10, right: 10, left: 0, bottom: 0 }}>
                  <CartesianGrid strokeDasharray="3 3" />
                  <XAxis dataKey="oni" type="number" domain={["auto", "auto"]} tickLine={false} axisLine={false} />
                  <YAxis dataKey="total" type="number" scale="log" domain={["auto", "auto"]} tickLine={false} axisLine={false} width={40} tickFormatter={(v) => formatCompact(v)} />
                  <ReferenceLine x={o.oni ?? 0} stroke={C.highlight} label={{ value: "now", position: "top", fontSize: 10, fill: C.highlight }} />
                  <ChartTooltip
                    content={({ active, payload }) => {
                      const d = active && payload?.[0]?.payload;
                      return d ? (
                        <div className="rounded-md border bg-popover/95 px-2 py-1 text-xs shadow">
                          {d.year}: ONI {d.oni > 0 ? "+" : ""}
                          {d.oni}, {formatInt(d.total)}
                        </div>
                      ) : null;
                    }}
                  />
                  <Scatter data={o.seasons} fill={C.measured} isAnimationActive={false}>
                    <LabelList dataKey="year" position="top" className="fill-muted-foreground text-[9px]" />
                  </Scatter>
                </ScatterChart>
              </ChartContainer>
            </Section>
          )}
        </>
      ) : o.usefulLeads.length ? (
        <Callout>
          No useful outlook for {formatPeriod(o.seasonStart)} yet: it is {o.lead} months away, and in tests the El Niño
          index predicted this area&apos;s season only up to {Math.max(...o.usefulLeads)} month
          {Math.max(...o.usefulLeads) > 1 ? "s" : ""} ahead.
        </Callout>
      ) : (
        <Callout>
          The El Niño index does <b>not</b> predict this area&apos;s fire season well: in tests on past seasons it was no
          better than guessing an average year at any lead time. Fire here depends more on local weather and land use.
        </Callout>
      )}
      <Section title="How the outlook works">
        <ol className="list-decimal space-y-1 pl-4 text-xs leading-relaxed text-muted-foreground">
          <li>The season is the 3 months with the most fire on average.</li>
          <li>The newest El Niño index (NOAA ONI) is compared with the same lead before every past season.</li>
          <li>A straight-line fit on the log of the season total gives the most likely total; the spread of past errors gives the chances of the three thirds.</li>
          <li>It is shown only if, predicting each past year without its own data, it beat &ldquo;always an average year&rdquo; (correlation ≥ 0.4, at least 10 % smaller errors).</li>
        </ol>
        <Note>For official outlooks see the ASEAN Specialised Meteorological Centre and national weather services.</Note>
      </Section>
    </div>
  );
}
