import type { AreaIndex, AreaMeta } from "@/lib/data/types";

/** Area id from the optional catch-all route segments (undefined or [] = Asia). */
export function areaIdFromSegments(segments: string[] | string | undefined): string {
  if (!segments) return "";
  const parts = Array.isArray(segments) ? segments : [segments];
  return parts.map((s) => decodeURIComponent(s)).join("/");
}

/** Route segments of an area id ("" -> []). */
export function segmentsFromAreaId(id: string): string[] {
  return id ? id.split("/") : [];
}

export function areaHref(id: string): string {
  return id ? `/${id}/` : "/";
}

export type AreaLookup = Map<string, AreaMeta>;

export function buildLookup(index: AreaIndex): AreaLookup {
  return new Map(index.areas.map((a) => [a.id, a]));
}

/** The area and its parents, outermost first. */
export function ancestry(lookup: AreaLookup, id: string): AreaMeta[] {
  const out: AreaMeta[] = [];
  let cur = lookup.get(id);
  while (cur) {
    out.unshift(cur);
    cur = cur.parent === null ? undefined : lookup.get(cur.parent);
  }
  return out;
}

/**
 * Which area's sub-area borders the map shows: the area itself when it has
 * sub-areas, else its parent (with the area highlighted).
 */
export function mapContextId(lookup: AreaLookup, id: string): string {
  const a = lookup.get(id);
  if (!a) return "";
  if (a.hasGeo) return a.id;
  return a.parent ?? "";
}

export const LEVEL_LABEL: Record<AreaMeta["level"], string> = {
  asia: "Continent",
  group: "Region",
  country: "Country",
  adm1: "State / province",
  adm2: "District",
};

export const CHILD_LABEL: Record<AreaMeta["level"], string> = {
  asia: "Countries",
  group: "Countries",
  country: "States / provinces",
  adm1: "Districts",
  adm2: "",
};

/** False for the study's areas outside Asia (top-level areas other than the "Asia" root, e.g. Argentina). */
export function inAsia(lookup: AreaLookup | undefined, id: string): boolean {
  if (!lookup) return true;
  return (ancestry(lookup, id)[0]?.level ?? "asia") === "asia";
}

/** The country an area belongs to (itself for a country; undefined above country level). */
export function countryOf(lookup: AreaLookup, id: string): string | undefined {
  let cur = lookup.get(id);
  while (cur && cur.level !== "country") cur = cur.parent === null ? undefined : lookup.get(cur.parent);
  return cur?.id;
}

/**
 * Box to frame on the map. Areas reaching across the 180° line (Russia's Chukotka, so also "Asia") get a box
 * from -180 to 180, which would zoom out to the whole world; frame them from their west edge to 180° instead.
 */
export function viewBBox(b: [number, number, number, number]): [number, number, number, number] {
  if (b[2] - b[0] <= 180) return b;
  return [Math.max(b[0], 19), b[1], 180, Math.min(b[3], 78)];
}
