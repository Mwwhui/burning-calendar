"use client";

import { Pause, Play } from "lucide-react";
import { useMemo, useRef } from "react";

import { Button } from "@/components/ui/button";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { Tooltip, TooltipContent, TooltipTrigger } from "@/components/ui/tooltip";
import { useCurrentArea } from "@/features/explorer/hooks/use-area";
import { useExplorer, type Speed } from "@/features/explorer/store";
import { useAreaDetail, usePlaybackFrames } from "@/lib/data/queries";
import type { PlaybackStep } from "@/lib/data/types";
import { cn } from "@/lib/utils";
import { formatDay, formatInt, formatPeriod } from "@/lib/format";

import { usePlaybackTicker } from "../hooks/use-playback";

const SPEEDS: Speed[] = ["slow", "normal", "fast"];

export function TimelineBar() {
  const { index, area, id } = useCurrentArea();
  const { step, speed, playing, setStep, setSpeed, setFrame, setPlaying } = useExplorer();
  const hasFrames = !!area?.frames.includes(step);
  const { data: frames, isLoading } = usePlaybackFrames(area ? id : undefined, step, hasFrames);
  const { data: detail } = useAreaDetail(area ? id : undefined);
  const periods = frames?.periods ?? [];
  const { current, togglePlay } = usePlaybackTicker(periods.length);

  /** periods holding converted (estimated) months */
  const estimated = useMemo(() => {
    const s = new Set<string>();
    if (!detail) return s;
    detail.series.months.forEach((m, i) => {
      if (detail.series.estimated[i]) s.add(step === "year" ? m.slice(0, 4) : m);
    });
    return s;
  }, [detail, step]);

  const totals = frames?.totals ?? [];
  const max = Math.max(1, ...totals.map((t) => t ?? 0));
  const barsRef = useRef<HTMLDivElement>(null);

  function scrub(clientX: number) {
    const el = barsRef.current;
    if (!el || periods.length === 0) return;
    const r = el.getBoundingClientRect();
    const i = Math.floor(((clientX - r.left) / r.width) * periods.length);
    setPlaying(false);
    setFrame(Math.max(0, Math.min(periods.length - 1, i)));
  }

  const label = periods[current];
  const total = totals[current];

  return (
    <div className="absolute inset-x-3 bottom-3 z-10 rounded-xl border bg-background/88 p-3 shadow-lg backdrop-blur-md">
      <div className="flex items-center gap-3">
        <Tooltip>
          <TooltipTrigger
            render={
              <Button
                size="icon-lg"
                className="shrink-0 rounded-full"
                onClick={togglePlay}
                disabled={periods.length === 0}
                aria-label={playing ? "Pause" : "Play"}
              />
            }
          >
            {playing ? <Pause /> : <Play className="translate-x-px" />}
          </TooltipTrigger>
          <TooltipContent>{playing ? "Pause (space)" : "Play from the start (space)"}</TooltipContent>
        </Tooltip>

        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-baseline gap-x-2">
            <span className="text-xl font-semibold tabular-nums">{label ? formatPeriod(label) : "–"}</span>
            <span className="text-sm text-muted-foreground tabular-nums">
              {total !== undefined && total !== null ? `${formatInt(total)} ${index?.unit ?? "fire days"}` : ""}
            </span>
            {label && estimated.has(label) && (
              <span className="rounded bg-amber-500/15 px-1.5 text-[11px] font-medium text-amber-600 dark:text-amber-400">
                estimate
              </span>
            )}
            {label && label === frames?.partial && (
              <span className="rounded bg-sky-500/15 px-1.5 text-[11px] font-medium text-sky-700 dark:text-sky-300">
                to {formatDay(index?.lastDay)}
              </span>
            )}
          </div>
        </div>

        <div className="hidden items-center gap-2 sm:flex">
          <ToggleGroup
            size="sm"
            variant="outline"
            value={[step]}
            onValueChange={(v) => v[0] && setStep(v[0] as PlaybackStep)}
          >
            <ToggleGroupItem value="year">Year</ToggleGroupItem>
            <ToggleGroupItem value="month">Month</ToggleGroupItem>
          </ToggleGroup>
          <Button
            size="sm"
            variant="outline"
            className="w-[76px] capitalize"
            onClick={() => setSpeed(SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length])}
            aria-label="Playback speed"
          >
            {speed}
          </Button>
        </div>
      </div>

      {/* sparkline: one bar per period, click or drag to jump */}
      <div
        ref={barsRef}
        role="slider"
        tabIndex={0}
        aria-label="Period"
        aria-valuemin={0}
        aria-valuemax={Math.max(0, periods.length - 1)}
        aria-valuenow={current}
        aria-valuetext={label}
        className="mt-2.5 flex h-12 cursor-pointer touch-none items-end gap-px"
        onPointerDown={(e) => {
          e.currentTarget.setPointerCapture(e.pointerId);
          scrub(e.clientX);
        }}
        onPointerMove={(e) => e.buttons === 1 && scrub(e.clientX)}
      >
        {isLoading && <div className="h-full w-full animate-pulse rounded bg-muted" />}
        {!isLoading && periods.length === 0 && (
          <div className="self-center text-xs text-muted-foreground">Too few fires here to play back.</div>
        )}
        {periods.map((p, i) => {
          const h = Math.max(2, ((totals[i] ?? 0) / max) * 100);
          return (
            <div
              key={p}
              title={`${formatPeriod(p)}: ${formatInt(totals[i])}${estimated.has(p) ? " (estimate)" : ""}`}
              className={cn(
                "flex-1 rounded-t-[2px] transition-colors",
                i === current
                  ? "bg-orange-500"
                  : i < current
                    ? estimated.has(p)
                      ? "bg-orange-400/45"
                      : "bg-orange-400/80"
                    : estimated.has(p)
                      ? "bg-muted-foreground/25"
                      : "bg-muted-foreground/45",
              )}
              style={{ height: `${h}%` }}
            />
          );
        })}
      </div>
      <div className="mt-1 flex justify-between text-[10px] text-muted-foreground tabular-nums">
        <span>{periods[0] ? formatPeriod(periods[0]) : ""}</span>
        <span className="hidden sm:inline">
          Faded bars: estimated from older satellites (MODIS / Suomi NPP), converted to NOAA-20 terms
        </span>
        <span>{periods.length ? formatPeriod(periods[periods.length - 1]) : ""}</span>
      </div>
    </div>
  );
}
