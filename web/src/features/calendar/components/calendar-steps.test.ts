import { describe, expect, it } from "vitest";

import { amountEdges } from "./calendar-heatmap";

describe("calendar colour steps", () => {
  it("uses 7 rising, nicely rounded edges up to the maximum", () => {
    const e = amountEdges(1400);
    expect(e).toHaveLength(7);
    expect(e[0]).toBe(0);
    for (let i = 1; i < e.length; i++) expect(e[i]).toBeGreaterThan(e[i - 1]);
    for (const x of e.slice(1)) expect(String(x)).toMatch(/^[125]0*$/);
    expect(e[e.length - 1]).toBeLessThanOrEqual(1400);
  });
  it("copes with tiny areas", () => {
    expect(amountEdges(0)).toHaveLength(7);
    expect(new Set(amountEdges(3)).size).toBe(7);
  });
});
