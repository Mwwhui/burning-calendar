"use client";

import { MapPin, Search } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import {
  Command,
  CommandDialog,
  CommandEmpty,
  CommandGroup,
  CommandInput,
  CommandItem,
  CommandList,
} from "@/components/ui/command";
import { useCurrentArea } from "@/features/explorer/hooks/use-area";
import { ancestry, areaHref, LEVEL_LABEL } from "@/lib/area";
import type { AreaMeta } from "@/lib/data/types";

const ORDER: AreaMeta["level"][] = ["asia", "group", "country", "adm1", "adm2"];

/** Search box for every listed area (Ctrl/⌘ K). */
export function AreaSearch() {
  const router = useRouter();
  const { index, lookup } = useCurrentArea();
  const [open, setOpen] = useState(false);

  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if ((e.key === "k" || e.key === "K") && (e.metaKey || e.ctrlKey)) {
        e.preventDefault();
        setOpen((o) => !o);
      } else if (e.key === "/" && !open && !(e.target instanceof HTMLInputElement)) {
        e.preventDefault();
        setOpen(true);
      }
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const groups = useMemo(() => {
    if (!index || !lookup) return [];
    return ORDER.map((level) => ({
      level,
      items: index.areas
        .filter((a) => a.level === level && !a.empty)
        .map((a) => ({
          area: a,
          // parents without the "Asia" root (areas outside Asia, e.g. Argentina, start at their country)
          path: ancestry(lookup, a.id)
            .filter((p) => p.level !== "asia")
            .slice(0, -1)
            .map((p) => p.name)
            .join(" › "),
        })),
    })).filter((g) => g.items.length);
  }, [index, lookup]);

  return (
    <>
      <Button
        variant="outline"
        className="h-9 w-full min-w-0 justify-start gap-2 text-muted-foreground sm:w-72"
        onClick={() => setOpen(true)}
      >
        <Search className="size-4" />
        <span className="flex-1 truncate text-left">Search a country, state or district…</span>
        <kbd className="hidden rounded border bg-muted px-1.5 font-mono text-[10px] sm:inline">Ctrl K</kbd>
      </Button>
      <CommandDialog open={open} onOpenChange={setOpen} title="Find an area" description="Search the listed areas">
        <Command>
          <CommandInput placeholder="Type a place, e.g. Sarawak or Riau…" />
        <CommandList className="max-h-[60vh]">
          <CommandEmpty>No area with that name.</CommandEmpty>
          {groups.map((g) => (
            <CommandGroup key={g.level} heading={LEVEL_LABEL[g.level]}>
              {g.items.map(({ area, path }) => (
                <CommandItem
                  key={area.id || "asia"}
                  value={`${area.name} ${path} ${area.id}`}
                  onSelect={() => {
                    setOpen(false);
                    router.push(areaHref(area.id));
                  }}
                >
                  <MapPin className="text-muted-foreground" />
                  <span>{area.name}</span>
                  {path && <span className="truncate text-xs text-muted-foreground">{path}</span>}
                </CommandItem>
              ))}
            </CommandGroup>
          ))}
        </CommandList>
        </Command>
      </CommandDialog>
    </>
  );
}
