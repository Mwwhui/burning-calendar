"use client";

import Link from "next/link";

import { useCurrentArea } from "@/features/explorer/hooks/use-area";
import { ancestry, areaHref } from "@/lib/area";
import { cn } from "@/lib/utils";

import { topAreas } from "../lib/top-areas";

/** Switch between the study's top-level areas (Asia, Argentina), shown only when there is more than one. */
export function StudySwitch() {
  const { index, lookup, id } = useCurrentArea();
  if (!index || !lookup) return null;
  const tops = topAreas(index.areas);
  if (tops.length < 2) return null;
  const current = ancestry(lookup, id)[0]?.id ?? "";
  return (
    <nav aria-label="Study area" className="hidden items-center rounded-md border bg-muted/40 p-0.5 md:flex">
      {tops.map((a) => (
        <Link
          key={a.id || "asia"}
          href={areaHref(a.id)}
          aria-current={a.id === current ? "page" : undefined}
          className={cn(
            "rounded px-2.5 py-1 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground",
            a.id === current && "bg-background text-foreground shadow-sm",
          )}
        >
          {a.name}
        </Link>
      ))}
    </nav>
  );
}
