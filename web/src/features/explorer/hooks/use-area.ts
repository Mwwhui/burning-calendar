"use client";

import { useParams } from "next/navigation";
import { useMemo } from "react";

import { areaIdFromSegments, buildLookup, type AreaLookup } from "@/lib/area";
import { useAreaIndex } from "@/lib/data/queries";
import type { AreaIndex, AreaMeta } from "@/lib/data/types";

/** Current area id from the URL (works in layouts and pages). */
export function useAreaId(): string {
  const params = useParams<{ area?: string[] }>();
  return areaIdFromSegments(params.area);
}

export interface AreaContext {
  index: AreaIndex | undefined;
  lookup: AreaLookup | undefined;
  area: AreaMeta | undefined;
  id: string;
}

export function useCurrentArea(): AreaContext {
  const id = useAreaId();
  const { data: index } = useAreaIndex();
  const lookup = useMemo(() => (index ? buildLookup(index) : undefined), [index]);
  return { index, lookup, area: lookup?.get(id), id };
}
