import type { PlaybackStep } from "./types";

/** Base URL of the exported data (public/data). */
export const DATA_BASE = "/data";

/** File name of an area id ("" is the whole of Asia). */
export function fileId(areaId: string): string {
  return areaId || "_all";
}

export const dataUrl = {
  index: () => `${DATA_BASE}/index.json`,
  area: (id: string) => `${DATA_BASE}/area/${fileId(id)}.json`,
  frames: (id: string, step: PlaybackStep) => `${DATA_BASE}/frames/${fileId(id)}.${step}.json`,
  geo: (id: string) => `${DATA_BASE}/geo/${fileId(id)}.json`,
  detail: (id: string) => `${DATA_BASE}/detail/${fileId(id)}.json`,
  eventDots: (eventId: number) => `${DATA_BASE}/event-dots/${eventId}.json`,
  events: (id: string) => `${DATA_BASE}/events/${fileId(id)}.json`,
  daily: (id: string) => `${DATA_BASE}/daily/${fileId(id)}.json`,
  totals: (id: string) => `${DATA_BASE}/totals/${fileId(id)}.json`,
  cells: (iso: string) => `${DATA_BASE}/cells/${iso.toLowerCase()}.json`,
  recent: (iso: string) => `${DATA_BASE}/recent/${iso.toLowerCase()}.json`,
  asmc: () => `${DATA_BASE}/asmc.json`,
  alerts: () => `${DATA_BASE}/alerts.json`,
  land: (id: string) => `${DATA_BASE}/land/${fileId(id)}.json`,
  spots: (id: string) => `${DATA_BASE}/spots/${fileId(id)}.json`,
  forecast: (id: string) => `${DATA_BASE}/forecast/${fileId(id)}.json`,
  concessions: () => `${DATA_BASE}/land/_concessions.json`,
};
