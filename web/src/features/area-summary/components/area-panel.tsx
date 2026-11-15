"use client";

import { ChevronRight, PenLine, X } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef } from "react";

import { Callout, Empty, Section } from "@/components/common/section";
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { CalendarHeatmap } from "@/features/calendar/components/calendar-heatmap";
import { ChecksView } from "@/features/checks/components/checks-view";
import { DatesView } from "@/features/dates/components/dates-view";
import { DataView } from "@/features/downloads/components/data-view";
import { WatchButton } from "@/features/alerts/components/watch-button";
import { EventsView } from "@/features/events/components/events-view";
import { ForecastCard, ForecastSection } from "@/features/forecast/components/forecast-view";
import { LandView } from "@/features/land/components/land-view";
import { useCurrentArea } from "@/features/explorer/hooks/use-area";
import { useAreaData } from "@/features/explorer/hooks/use-area-data";
import { useExplorer, type PanelTab } from "@/features/explorer/store";
import { MethodUnavailable, MethodView } from "@/features/method/components/method-view";
import { OutlookView } from "@/features/outlook/components/outlook-view";
import { PeatView } from "@/features/peat/components/peat-view";
import { SubAreaList } from "@/features/sub-areas/components/sub-area-list";
import { CumulativeChart, YearlyBars } from "@/features/trends/components/trends-view";
import { ancestry, areaHref, CHILD_LABEL, countryOf, inAsia, LEVEL_LABEL } from "@/lib/area";
import { useExtraDetail, usePlaybackFrames, useUpdateStatus } from "@/lib/data/queries";
import { formatDay, formatInt } from "@/lib/format";
import { downloadDataUrl, elementToPng } from "@/lib/image-export";
import { cn } from "@/lib/utils";

import { fireBrief } from "../lib/brief";
import { TabBar } from "./tab-bar";
import { ConsistencyCard } from "./consistency-card";
import { Headline, Metrics } from "./metrics";
import { MonthToDate } from "./month-to-date";

const TABS: { id: PanelTab; label: string }[] = [
  { id: "overview", label: "Overview" },
  { id: "calendar", label: "Calendar" },
  { id: "trends", label: "Trends" },
  { id: "dates", label: "Dates" },
  { id: "events", label: "Fire events" },
  { id: "land", label: "Land use" },
  { id: "outlook", label: "Forecast" },
  { id: "peat", label: "Peat" },
  { id: "checks", label: "Checks" },
  { id: "method", label: "Method" },
  { id: "data", label: "Data" },
];

/** Right-hand panel: what the selected (or drawn) area's fire record says. */
export function AreaPanel() {
  const { index, lookup, area, id } = useCurrentArea();
  const { detail, isLoading, isError, own, listedId, ownInfo } = useAreaData();
  const { step, frame, tab, ownArea, setStep, setFrame, setLayer, setPlaying, setTab, setOwnArea, setDraw } = useExplorer();
  const { data: yearFrames } = usePlaybackFrames(area ? id : undefined, "year", !!area?.frames.includes("year"));
  const { data: monthFrames } = usePlaybackFrames(area ? id : undefined, "month", tab === "calendar" && !!area?.frames.includes("month"));
  const needsExtra = !own && ["overview", "outlook", "peat", "checks", "method"].includes(tab);
  const { data: extra } = useExtraDetail(needsExtra ? listedId : undefined);

  const rootRef = useRef<HTMLDivElement>(null);
  // "Save this view as image" (Data tab): the panel without its tab bar and buttons
  useEffect(() => {
    async function save() {
      const el = rootRef.current;
      if (!el) return;
      const png = await elementToPng(el, (n) => n.getAttribute("role") !== "tablist" && n.tagName !== "BUTTON" && !n.hasAttribute("data-noexport"));
      const name = (area?.name || "asia").replace(/[^a-zA-Z0-9]+/g, "_");
      downloadDataUrl(`view_${name}_${tab}.png`, png);
    }
    const h = () => void save();
    window.addEventListener("burning-calendar:save-view", h);
    return () => window.removeEventListener("burning-calendar:save-view", h);
  }, [area?.name, tab]);

  const activeYear =
    step === "year" && yearFrames ? Number(yearFrames.periods[frame ?? yearFrames.periods.length - 1]) : undefined;

  function pickYear(year: number) {
    const i = yearFrames?.periods.indexOf(String(year)) ?? -1;
    if (i < 0) return;
    setLayer("playback");
    if (step !== "year") setStep("year");
    setPlaying(false);
    setFrame(i);
  }

  /** show one month on the map: month by month when it is in the month frames, else its year */
  function showMonth(month: string) {
    const i = monthFrames?.periods.indexOf(month) ?? -1;
    if (i < 0) return pickYear(Number(month.slice(0, 4)));
    setLayer("playback");
    setPlaying(false);
    if (step !== "month") setStep("month");
    // setStep resets the frame, so set it after
    setTimeout(() => setFrame(i), 0);
  }

  if (!index || !lookup) return <PanelSkeleton />;
  if (!area) {
    return (
      <div className="p-5 text-sm text-muted-foreground">
        This area is not in the exported data.{" "}
        <Link href="/" className="underline">
          Back to Asia
        </Link>
      </div>
    );
  }

  const trail = ancestry(lookup, id);
  const s = detail?.summary ?? null;
  const unit = index.unit;
  const canDraw = !!lookup && !!countryOf(lookup, id) && !!lookup.get(countryOf(lookup, id)!)?.cells;
  const eventsId = own ? ownArea?.countryId : area.events ? id : undefined;

  return (
    <div ref={rootRef} className="@container flex min-h-full flex-col bg-background">
      {/* header */}
      <header className="space-y-2 px-5 pt-5 pb-3">
        <nav aria-label="Breadcrumb" className="flex flex-wrap items-center gap-0.5 text-xs text-muted-foreground">
          {trail.slice(0, own ? undefined : -1).map((a) => (
            <span key={a.id || "asia"} className="flex items-center gap-0.5">
              <Link href={areaHref(a.id)} onClick={() => setOwnArea(null)} className="hover:text-foreground hover:underline">
                {a.name}
              </Link>
              <ChevronRight className="size-3" />
            </span>
          ))}
          <span className="text-foreground">{own ? "Your area" : LEVEL_LABEL[area.level]}</span>
        </nav>
        <div className="flex items-start justify-between gap-2">
          <h1 className="text-2xl leading-tight font-semibold tracking-tight">{own ? (ownArea?.label ?? "Your area") : area.name}</h1>
          {own ? (
            <Button size="xs" variant="outline" onClick={() => setOwnArea(null)}>
              <X /> Clear
            </Button>
          ) : (
            <div className="flex shrink-0 items-center gap-1">
              <WatchButton areaId={area.id} />
              {canDraw && (
                <Button size="xs" variant="ghost" className="text-muted-foreground" onClick={() => setDraw("rectangle")}>
                  <PenLine /> Draw area
                </Button>
              )}
            </div>
          )}
        </div>
        {own && ownInfo && (
          <p className="text-xs text-muted-foreground">
            About {formatInt(ownInfo.km2)} km² in {ownInfo.country}, {ownInfo.nCells} cells of 0.1° with fire.
          </p>
        )}
        {s && <Headline s={s} />}
      </header>

      {/* tabs */}
      <div className="sticky top-0 z-10 border-y bg-background/95 backdrop-blur">
        <TabBar tabs={TABS} value={tab} onChange={setTab} />
      </div>

      <div className="flex-1 space-y-5 p-5">
        {isLoading && <PanelSkeleton compact />}
        {isError && <Callout tone="warn">Could not load this area&apos;s data.</Callout>}
        {area.empty && !own && <Empty>Too few fires here to build a record.</Empty>}

        {detail && (
          <>
            {tab === "overview" && (
              <>
                {!own && listedId !== undefined && index.lastDay && (
                  <MonthToDate listedId={listedId} series={detail.series} lastDay={index.lastDay} />
                )}
                {!own && area.forecast && <ForecastCard areaId={area.id} />}
                {s ? <Metrics s={s} unit={unit} /> : <Empty>Too little data for a summary.</Empty>}
                {!own && extra && extra.seams.rows.length > 0 && <ConsistencyCard annual={detail.annual} extra={extra} />}
                {s && (
                  <section aria-label="Fire brief" className="space-y-1.5 rounded-xl border bg-gradient-to-b from-orange-500/[0.06] to-transparent p-3.5 text-sm leading-relaxed">
                    {fireBrief(own ? "Your area" : area.name, s, unit, index.enso[String(s.thisYear)], inAsia(lookup, id)).map((p) => (
                      <p key={p}>{p}</p>
                    ))}
                  </section>
                )}
                {own && (
                  <Callout>
                    Drawn areas use their country&apos;s conversion: each month&apos;s harmonized total is shared out by where
                    the satellites saw fire, then the cells inside your shape are added up.
                  </Callout>
                )}
                {detail.notes.tooFewFrom && (
                  <Callout tone="warn">
                    Too few fires to convert the older satellites here, so the record starts in {detail.notes.tooFewFrom}.
                  </Callout>
                )}
                {detail.notes.roughYearsPct !== null && (
                  <Callout tone="warn">
                    Years 2003–2011 are rough here (±{Math.round(detail.notes.roughYearsPct)} %): compare them as a group,
                    not one by one.
                  </Callout>
                )}
                {!own && area.children.length > 0 && (
                  <Section title={CHILD_LABEL[area.level]}>
                    <SubAreaList area={area} lookup={lookup} change={detail.childChange} />
                  </Section>
                )}
              </>
            )}
            {tab === "calendar" && (
              <Section
                title="Fire calendar"
                description="Each row is a year, each column a month; darker = more fire. Point at or tap a month for its numbers."
              >
                <CalendarHeatmap
                  series={detail.series}
                  partialMonth={s?.partialMonth ?? null}
                  enso={index.enso}
                  activeYear={activeYear}
                  onPickYear={pickYear}
                  onShowMonth={own ? undefined : showMonth}
                />
              </Section>
            )}
            {tab === "trends" && (
              <>
                {s && <CumulativeChart series={detail.series} summary={s} enso={index.enso} />}
                <YearlyBars annual={detail.annual} activeYear={activeYear} onPickYear={pickYear} />
              </>
            )}
            {tab === "dates" && index.lastDay && (
              <DatesView listedId={own ? undefined : listedId} series={detail.series} lastDay={index.lastDay} name={own ? "my_area" : area.name} />
            )}
            {tab === "events" && <EventsView eventsId={eventsId} ring={own ? ownArea?.ring : undefined} />}
            {tab === "land" &&
              (own ? (
                <Empty>Land use is shown for listed areas; open the country, state or district around your shape.</Empty>
              ) : (
                <LandView area={area} />
              ))}
            {tab === "outlook" &&
              (own ? (
                <MethodUnavailable />
              ) : (
                <div className="space-y-7">
                  {area.forecast && <ForecastSection areaId={area.id} />}
                  <div className="space-y-3">
                    <h3 className="text-sm font-semibold tracking-tight">Seasonal outlook (El Niño)</h3>
                    <OutlookView o={extra?.outlook} unit={unit} />
                  </div>
                </div>
              ))}
            {tab === "peat" && (own ? <MethodUnavailable /> : extra ? <PeatView p={extra.peat} /> : <PanelSkeleton compact />)}
            {tab === "checks" && (own ? <MethodUnavailable /> : extra ? <ChecksView official={extra.official} gfed={extra.gfed} asia={inAsia(lookup, id)} /> : <PanelSkeleton compact />)}
            {tab === "method" && (own ? <MethodUnavailable /> : <MethodView series={detail.series} extra={extra} />)}
            {tab === "data" && <DataView detail={detail} area={area} own={own} lastDay={index.lastDay} />}
          </>
        )}
      </div>

      <footer className="space-y-1 border-t px-5 py-3 text-[11px] text-muted-foreground">
        <p>
          Unit: <b>fire days</b> — about 1 km cells with at least one fire detection that day, in NOAA-20 VIIRS terms.
          Older satellites (MODIS, Suomi NPP) are converted, with a likely range.
        </p>
        <p>
          Data: NASA FIRMS, to {formatDay(index.lastDay)}
          <UpdatedNote />. Not an official product.{" "}
          <Link href="/method/" className="underline hover:text-foreground">
            How it works
          </Link>
        </p>
      </footer>
    </div>
  );
}

function PanelSkeleton({ compact = false }: { compact?: boolean }) {
  return (
    <div className={cn("space-y-3", !compact && "p-5")}>
      {!compact && <Skeleton className="h-8 w-2/3" />}
      <div className="grid grid-cols-2 gap-2">
        {[0, 1, 2, 3].map((i) => (
          <Skeleton key={i} className="h-16" />
        ))}
      </div>
      <Skeleton className="h-24" />
      <Skeleton className="h-64" />
    </div>
  );
}

function UpdatedNote() {
  const { data } = useUpdateStatus();
  if (!data?.finished) return null;
  const d = new Date(data.finished);
  return (
    <>
      {" "}
      · updated {d.toLocaleDateString("en-GB", { day: "numeric", month: "short" })}{" "}
      {d.toLocaleTimeString("en-GB", { hour: "2-digit", minute: "2-digit" })}
      {data.ok ? "" : " (last update failed)"}
    </>
  );
}
