/** Side panel width limits (desktop layout), in CSS pixels. */
export const PANEL_MIN = 360;
export const PANEL_DEFAULT = 480;
export const PANEL_KEY = "panel-width";

/** Largest panel width that still leaves the map at least `mapMin` px (and never over 70 % of the window). */
export function panelMax(viewport: number, mapMin = 420): number {
  return Math.max(PANEL_MIN, Math.min(viewport - mapMin, Math.round(viewport * 0.7)));
}

export function clampPanel(width: number, viewport: number): number {
  return Math.round(Math.min(panelMax(viewport), Math.max(PANEL_MIN, width)));
}
