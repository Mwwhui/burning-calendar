"use client";

import { Bell, BellOff } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useAlerts } from "@/lib/data/queries";
import { useIsClient } from "@/lib/use-is-client";

import { isWatched, useWatchlist } from "../watchlist";

/** Watch / unwatch an area; shows how many alerts it (or anything inside it) has now. */
export function WatchButton({ areaId }: { areaId: string }) {
  const ids = useWatchlist((s) => s.ids);
  const toggle = useWatchlist((s) => s.toggle);
  const { data } = useAlerts();
  const client = useIsClient();
  const watching = client && ids.includes(areaId);
  const n = (data?.alerts ?? []).filter((a) => isWatched(a, [areaId])).length;
  return (
    <Button
      size="xs"
      variant={watching ? "secondary" : "ghost"}
      className={watching ? "" : "text-muted-foreground"}
      onClick={() => toggle(areaId)}
      title={watching ? "Stop watching this area" : "Get this area's alerts in the bell and as browser notifications"}
    >
      {watching ? <BellOff /> : <Bell />} {watching ? "Watching" : "Watch"}
      {n > 0 && <span className="rounded-full bg-red-600 px-1.5 text-[10px] font-semibold text-white">{n}</span>}
    </Button>
  );
}
