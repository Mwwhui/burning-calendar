import { describe, expect, it } from "vitest";

import { clampPanel, PANEL_MIN, panelMax } from "./panel-width";

describe("panel width", () => {
  it("keeps the panel between its minimum and a size that leaves room for the map", () => {
    expect(clampPanel(100, 1600)).toBe(PANEL_MIN);
    expect(clampPanel(700, 1600)).toBe(700);
    expect(panelMax(1600)).toBe(1120);
    expect(clampPanel(5000, 1600)).toBe(1120);
    expect(clampPanel(600, 800)).toBe(PANEL_MIN + 20); // 800 - 420 map
  });
});
