"use client";

import { useQuery } from "@tanstack/react-query";

import { DATA_BASE as DATA_BASE_URL, dataUrl } from "./paths";
import type {
  AreaExtraDetail,
  AsmcData,
  CellsData,
  DailyData,
  EventDots,
  EventsData,
  TotalsData,
  RecentData,
  LandData,
  ForecastData,
  AlertsData,
  SpotsData,
  ConcessionFeatureCollection,
  AreaDetail,
  AreaFeatureCollection,
  AreaIndex,
  PlaybackFrames,
  PlaybackStep,
} from "./types";

async function getJson<T>(url: string): Promise<T> {
  const res = await fetch(url);
  if (!res.ok) throw new Error(`${res.status} ${res.statusText}: ${url}`);
  return (await res.json()) as T;
}

/** The exported files never change while the page is open. */
const STATIC = { staleTime: Infinity, gcTime: 30 * 60_000 } as const;

export function useAreaIndex() {
  return useQuery({
    queryKey: ["index"],
    queryFn: () => getJson<AreaIndex>(dataUrl.index()),
    ...STATIC,
  });
}

export function useAreaDetail(id: string | undefined) {
  return useQuery({
    queryKey: ["area", id],
    queryFn: () => getJson<AreaDetail>(dataUrl.area(id!)),
    enabled: id !== undefined,
    ...STATIC,
  });
}

export function usePlaybackFrames(id: string | undefined, step: PlaybackStep, enabled = true) {
  return useQuery({
    queryKey: ["frames", id, step],
    queryFn: () => getJson<PlaybackFrames>(dataUrl.frames(id!, step)),
    enabled: id !== undefined && enabled,
    ...STATIC,
  });
}

export function useAreaGeo(id: string | undefined) {
  return useQuery({
    queryKey: ["geo", id],
    queryFn: () => getJson<AreaFeatureCollection>(dataUrl.geo(id!)),
    enabled: id !== undefined,
    ...STATIC,
  });
}

function useStatic<T>(key: unknown[], url: string | undefined) {
  return useQuery({
    queryKey: key,
    queryFn: () => getJson<T>(url!),
    enabled: url !== undefined,
    ...STATIC,
  });
}

export const useExtraDetail = (id: string | undefined) =>
  useStatic<AreaExtraDetail>(["detail", id], id === undefined ? undefined : dataUrl.detail(id));
export const useEventDots = (eventId: number | undefined) =>
  useStatic<EventDots>(["event-dots", eventId], eventId === undefined ? undefined : dataUrl.eventDots(eventId));
export const useEvents = (id: string | undefined) =>
  useStatic<EventsData>(["events", id], id === undefined ? undefined : dataUrl.events(id));
export const useDaily = (id: string | undefined) =>
  useStatic<DailyData>(["daily", id], id === undefined ? undefined : dataUrl.daily(id));
export const useTotals = (id: string | undefined) =>
  useStatic<TotalsData>(["totals", id], id === undefined ? undefined : dataUrl.totals(id));
export const useCells = (iso: string | undefined) =>
  useStatic<CellsData>(["cells", iso], iso === undefined ? undefined : dataUrl.cells(iso));
export const useRecent = (iso: string | undefined) =>
  useStatic<RecentData>(["recent", iso], iso === undefined ? undefined : dataUrl.recent(iso));
export const useAsmc = () => useStatic<AsmcData>(["asmc"], dataUrl.asmc());
export const useLand = (id: string | undefined) =>
  useStatic<LandData>(["land", id], id === undefined ? undefined : dataUrl.land(id));
export const useSpots = (id: string | undefined) =>
  useStatic<SpotsData>(["spots", id], id === undefined ? undefined : dataUrl.spots(id));
export const useConcessionShapes = (enabled: boolean) =>
  useStatic<ConcessionFeatureCollection>(["concessions"], enabled ? dataUrl.concessions() : undefined);
export const useForecast = (id: string | undefined) =>
  useStatic<ForecastData>(["forecast", id], id === undefined ? undefined : dataUrl.forecast(id));

/** Last daily update (web/public/data/update.json, written by scripts/update_daily.py); may not exist. */
export function useUpdateStatus() {
  return useQuery({
    queryKey: ["update"],
    queryFn: async () => {
      const r = await fetch(`${DATA_BASE_URL}/update.json`);
      if (!r.ok) return null;
      return (await r.json()) as { ok: boolean; finished: string; lastDay?: string };
    },
    retry: false,
    staleTime: Infinity,
  });
}

/** Alerts of the latest data update; re-checked every 30 minutes while the app is open. */
export function useAlerts() {
  return useQuery({
    queryKey: ["alerts"],
    queryFn: async () => {
      const r = await fetch(dataUrl.alerts(), { cache: "no-store" });
      return r.ok ? ((await r.json()) as AlertsData) : null;
    },
    retry: false,
    refetchInterval: 30 * 60_000,
    staleTime: 10 * 60_000,
  });
}
