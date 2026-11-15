import { describe, expect, it } from "vitest";

import type { AreaMeta } from "@/lib/data/types";

import { topAreas } from "./top-areas";

const a = (id: string, name: string, level: AreaMeta["level"], parent: string | null, empty = false) =>
  ({ id, name, level, parent, children: [], ...(empty ? { empty } : {}) }) as unknown as AreaMeta;

describe("topAreas", () => {
  it("lists areas without a parent, Asia first", () => {
    const out = topAreas([a("arg", "Argentina", "country", null), a("mys", "Malaysia", "country", "southeast-asia"), a("", "Asia", "asia", null), a("zz", "Zed", "country", null, true)]);
    expect(out.map((x) => x.id)).toEqual(["", "arg"]);
  });
});
