"use client";

import Link from "next/link";
import { useMemo } from "react";

import { changeCss } from "@/lib/colors";
import { areaHref, type AreaLookup } from "@/lib/area";
import type { AreaMeta, ChildChange } from "@/lib/data/types";
import { formatInt, formatPct, monthSpan } from "@/lib/format";

/** Sub-areas ranked by this year's fire, with the change vs a typical year. */
export function SubAreaList({
  area,
  lookup,
  change,
}: {
  area: AreaMeta;
  lookup: AreaLookup;
  change: ChildChange | null;
}) {
  const rows = useMemo(() => {
    return area.children
      .map((id) => ({ meta: lookup.get(id), row: change?.rows[id] }))
      .filter((r): r is { meta: AreaMeta; row: ChildChange["rows"][string] | undefined } => !!r.meta)
      .sort((a, b) => (b.row?.[0] ?? -1) - (a.row?.[0] ?? -1));
  }, [area, lookup, change]);
  const max = Math.max(1, ...rows.map((r) => r.row?.[0] ?? 0));

  return (
    <div>
      {change && (
        <p className="mb-2 text-[11px] text-muted-foreground">
          Fire days in {monthSpan(change.throughMonth)} {change.year}, and the change from the same months of a
          typical year ({change.baseYears[0]}–{change.baseYears[change.baseYears.length - 1]}). NOAA-20 only, no
          conversion.
        </p>
      )}
      <ul className="divide-y">
        {rows.map(({ meta, row }) => (
          <li key={meta.id}>
            <Link
              href={areaHref(meta.id)}
              className="grid grid-cols-[1fr_4.5rem_4rem] items-center gap-2 px-1 py-1.5 text-sm hover:bg-muted/60"
            >
              <span className="min-w-0">
                <span className="block truncate">{meta.name}</span>
                <span className="mt-0.5 block h-1 rounded-full bg-orange-400/70" style={{ width: `${((row?.[0] ?? 0) / max) * 100}%` }} />
              </span>
              <span className="text-right tabular-nums">{formatInt(row?.[0])}</span>
              <span
                className="rounded px-1 text-right text-xs tabular-nums"
                style={
                  row?.[2] !== null && row?.[2] !== undefined
                    ? { backgroundColor: changeCss(row[2]), color: Math.abs(row[2]) > 60 ? "white" : "#111" }
                    : undefined
                }
              >
                {row?.[2] === null || row?.[2] === undefined ? "–" : formatPct(row[2])}
              </span>
            </Link>
          </li>
        ))}
      </ul>
    </div>
  );
}
