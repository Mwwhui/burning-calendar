import { describe, expect, it } from "vitest";

import { ancestry, areaHref, areaIdFromSegments, buildLookup, mapContextId, segmentsFromAreaId, viewBBox } from "./area";
import type { AreaIndex, AreaMeta } from "./data/types";

const a = (id: string, parent: string | null, children: string[], hasGeo: boolean): AreaMeta => ({
  id, name: id || "Asia", level: "country", parent, children, bbox: null, hasGeo, frames: [],
});

const index: AreaIndex = {
  generated: "", lastDay: null, unit: "fire days", enso: {},
  areas: [
    a("", null, ["southeast-asia"], true),
    a("southeast-asia", "", ["mys"], true),
    a("mys", "southeast-asia", ["mys/sarawak"], true),
    a("mys/sarawak", "mys", ["mys/sarawak/miri"], true),
    a("mys/sarawak/miri", "mys/sarawak", [], false),
  ],
};

describe("area ids and routes", () => {
  it("round-trips ids and segments", () => {
    expect(areaIdFromSegments(undefined)).toBe("");
    expect(areaIdFromSegments(["mys", "sarawak"])).toBe("mys/sarawak");
    expect(segmentsFromAreaId("")).toEqual([]);
    expect(segmentsFromAreaId("mys/sarawak")).toEqual(["mys", "sarawak"]);
    expect(areaHref("")).toBe("/");
    expect(areaHref("mys/sarawak")).toBe("/mys/sarawak/");
  });
  it("walks up the tree", () => {
    const l = buildLookup(index);
    expect(ancestry(l, "mys/sarawak/miri").map((x) => x.id)).toEqual([
      "", "southeast-asia", "mys", "mys/sarawak", "mys/sarawak/miri",
    ]);
  });
  it("shows the parent's map for areas without sub-areas", () => {
    const l = buildLookup(index);
    expect(mapContextId(l, "mys")).toBe("mys");
    expect(mapContextId(l, "mys/sarawak/miri")).toBe("mys/sarawak");
  });
});

describe("viewBBox", () => {
  it("frames areas across the 180° line from their west edge", () => {
    expect(viewBBox([95, -11, 141, 6])).toEqual([95, -11, 141, 6]);
    expect(viewBBox([-180, -11, 180, 81.9])).toEqual([19, -11, 180, 78]);
  });
});
