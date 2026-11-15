"use client";

import { create } from "zustand";

import type { Ring } from "@/lib/analytics/own-area";
import type { HazeKind } from "@/lib/gibs";
import type { FireEvent, PlaybackStep } from "@/lib/data/types";

export type MapLayer = "playback" | "change" | "recent";
export type FireStyle = "glow" | "heat" | "columns";
export type Speed = "slow" | "normal" | "fast";
export type DrawMode = "off" | "rectangle" | "polygon";
export type PanelTab =
  | "overview"
  | "calendar"
  | "trends"
  | "dates"
  | "events"
  | "outlook"
  | "land"
  | "peat"
  | "checks"
  | "method"
  | "data";

export const FRAME_MS: Record<PlaybackStep, Record<Speed, number>> = {
  year: { slow: 1300, normal: 750, fast: 350 },
  month: { slow: 650, normal: 330, fast: 150 },
};

export interface OwnArea {
  ring: Ring;
  /** country whose cells it uses (ISO3, lower case = area id) */
  countryId: string;
  label: string;
}

interface ExplorerState {
  layer: MapLayer;
  fireStyle: FireStyle;
  step: PlaybackStep;
  speed: Speed;
  /** index into the current frames' periods; null = latest */
  frame: number | null;
  playing: boolean;
  tab: PanelTab;
  draw: DrawMode;
  ownArea: OwnArea | null;
  event: FireEvent | null;
  /** day of the selected fire shown on the map (0 = its first day); null = the whole fire */
  eventDay: number | null;
  /** date range for the "Dates" tab (ISO days), null = default */
  dates: [string, string] | null;
  /** "Latest fires" layer: show detections of the last N days */
  recentDays: number;
  /** map overlays drawn on top of any layer */
  showConcessions: boolean;
  showSpots: boolean;
  /** concession picked in the Land use tab (highlighted and zoomed on the map) */
  concession: { id: number; bbox: [number, number, number, number] } | null;
  /** a point to zoom to (repeat burn spot) */
  focus: { lon: number; lat: number } | null;
  /** real satellite photo under the fire (NASA GIBS): day shown and whether to add 30 m Landsat/Sentinel-2 */
  photo: SatPhoto | null;
  /** daily haze / smoke veil (NASA GIBS) */
  haze: HazeView | null;
  /** registered by the map: the current map as a PNG data URL */
  captureMap: (() => string | null) | null;
  setLayer: (layer: MapLayer) => void;
  setFireStyle: (s: FireStyle) => void;
  setStep: (step: PlaybackStep) => void;
  setSpeed: (speed: Speed) => void;
  setFrame: (frame: number | null) => void;
  setPlaying: (playing: boolean) => void;
  setTab: (tab: PanelTab) => void;
  setDraw: (draw: DrawMode) => void;
  setOwnArea: (a: OwnArea | null) => void;
  setEvent: (e: FireEvent | null) => void;
  setEventDay: (d: number | null) => void;
  setDates: (d: [string, string] | null) => void;
  setRecentDays: (n: number) => void;
  setShowConcessions: (v: boolean) => void;
  setShowSpots: (v: boolean) => void;
  setConcession: (c: { id: number; bbox: [number, number, number, number] } | null) => void;
  setFocus: (f: { lon: number; lat: number } | null) => void;
  setCaptureMap: (f: (() => string | null) | null) => void;
  setPhoto: (p: SatPhoto | null) => void;
  setHaze: (h: HazeView | null) => void;
}

export interface HazeView {
  date: string;
  kind: HazeKind;
}

export interface SatPhoto {
  /** ISO day of the picture */
  date: string;
  /** add 30 m HLS (Landsat 8/9, Sentinel-2) when zoomed in */
  detail: boolean;
  /** before / after pair of a fire event: [day before it started, day after it ended] */
  pair?: [string, string];
  /** the fire being looked at: used to search the days with a 30 m picture over it */
  fire?: { lon: number; lat: number; start: string; end: string };
  /** hide the fire dots so the ground (burn scar) can be seen */
  hideFire?: boolean;
  /** daily photo: true colour or short-wave infrared (sees through smoke, burn scars red-brown) */
  view?: "true" | "swir";
  /** OPERA vegetation loss (30 m, from 2023) on top */
  dist?: boolean;
}

/** UI state of the explorer that is not part of the URL (the area is the URL). */
export const useExplorer = create<ExplorerState>((set) => ({
  layer: "playback",
  fireStyle: "glow",
  step: "year",
  speed: "normal",
  frame: null,
  playing: false,
  tab: "overview",
  draw: "off",
  ownArea: null,
  event: null,
  eventDay: null,
  dates: null,
  recentDays: 7,
  showConcessions: false,
  showSpots: false,
  concession: null,
  focus: null,
  captureMap: null,
  photo: null,
  haze: null,
  setLayer: (layer) => set({ layer, playing: false }),
  setFireStyle: (fireStyle) => set({ fireStyle }),
  setStep: (step) => set({ step, frame: null, playing: false }),
  setSpeed: (speed) => set({ speed }),
  setFrame: (frame) => set({ frame }),
  setPlaying: (playing) => set({ playing }),
  setTab: (tab) => set({ tab }),
  setDraw: (draw) => set({ draw }),
  setOwnArea: (ownArea) => set({ ownArea, draw: "off", tab: "overview" }),
  setEvent: (event) => set({ event, eventDay: null }),
  setEventDay: (eventDay) => set({ eventDay }),
  setDates: (dates) => set({ dates }),
  setRecentDays: (recentDays) => set({ recentDays }),
  setShowConcessions: (showConcessions) => set({ showConcessions }),
  setShowSpots: (showSpots) => set({ showSpots }),
  setConcession: (concession) => set(concession ? { concession, showConcessions: true } : { concession }),
  setFocus: (focus) => set(focus ? { focus, showSpots: true } : { focus }),
  setCaptureMap: (captureMap) => set({ captureMap }),
  setPhoto: (photo) => set({ photo }),
  setHaze: (haze) => set({ haze }),
}));
