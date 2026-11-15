"use client";

import { useMemo } from "react";

import { ownAreaSeries, ringKm2 } from "@/lib/analytics/own-area";
import { summaryFor } from "@/lib/analytics/series";
import { useAreaDetail, useCells } from "@/lib/data/queries";
import type { AreaDetail } from "@/lib/data/types";

import { useExplorer } from "../store";
import { useCurrentArea } from "./use-area";

export interface AreaData {
  /** the listed area's record, or the own area's (built in the browser) */
  detail: AreaDetail | undefined;
  isLoading: boolean;
  isError: boolean;
  /** an own (drawn) area is shown */
  own: boolean;
  /** listed area id whose extra files (detail, events, daily) apply; undefined for own areas */
  listedId: string | undefined;
  ownInfo?: { nCells: number; km2: number; country: string };
}

/** Record shown in the panel: the URL's area, or the drawn own area on top of it. */
export function useAreaData(): AreaData {
  const { area, id, lookup } = useCurrentArea();
  const ownArea = useExplorer((s) => s.ownArea);
  const listed = useAreaDetail(area && !area.empty ? id : undefined);
  const country = useAreaDetail(ownArea ? ownArea.countryId : undefined);
  const cells = useCells(ownArea ? ownArea.countryId : undefined);

  const own = useMemo(() => {
    if (!ownArea || !country.data || !cells.data) return undefined;
    const r = ownAreaSeries(cells.data, ownArea.ring, country.data.series, country.data.annual);
    const partial = country.data.summary?.partialMonth ?? null;
    const detail: AreaDetail = {
      id: "",
      name: ownArea.label,
      level: "adm2",
      series: r.series,
      annual: r.annual,
      summary: summaryFor(r.series, partial, r.annual),
      notes: { tooFewFrom: null, roughYearsPct: null },
      childChange: null,
    };
    return {
      detail,
      info: { nCells: r.nCells, km2: ringKm2(ownArea.ring), country: lookup?.get(ownArea.countryId)?.name ?? "" },
    };
  }, [ownArea, country.data, cells.data, lookup]);

  if (ownArea) {
    return {
      detail: own?.detail,
      isLoading: country.isLoading || cells.isLoading,
      isError: country.isError || cells.isError,
      own: true,
      listedId: undefined,
      ownInfo: own?.info,
    };
  }
  return {
    detail: listed.data,
    isLoading: listed.isLoading,
    isError: listed.isError,
    own: false,
    listedId: area && !area.empty ? id : undefined,
  };
}
