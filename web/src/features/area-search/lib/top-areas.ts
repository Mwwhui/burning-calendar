import type { AreaMeta } from "@/lib/data/types";

/** Top-level areas (no parent), "Asia" first, the others (e.g. Argentina) by name. */
export function topAreas(areas: AreaMeta[]): AreaMeta[] {
  return areas
    .filter((a) => a.parent === null && !a.empty)
    .sort((a, b) => (a.level === "asia" ? -1 : b.level === "asia" ? 1 : a.name.localeCompare(b.name)));
}
