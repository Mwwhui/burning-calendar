"use client";

import { Bell, BellRing, Flame, TrendingUp, Zap } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import { Button } from "@/components/ui/button";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { areaHref } from "@/lib/area";
import { useAlerts } from "@/lib/data/queries";
import type { AlertItem } from "@/lib/data/types";
import { formatDay } from "@/lib/format";
import { useIsClient } from "@/lib/use-is-client";
import { cn } from "@/lib/utils";

import { isWatched, useWatchlist } from "../watchlist";

const KIND_ICON = { surge: TrendingUp, forecast: Zap, big_fire: Flame };

/** Header bell: alerts for watched areas, the strongest across Asia, and browser notifications. */
export function AlertsBell() {
  const router = useRouter();
  const { data } = useAlerts();
  const ids = useWatchlist((s) => s.ids);
  const notified = useWatchlist((s) => s.notified);
  const setNotified = useWatchlist((s) => s.setNotified);
  const [open, setOpen] = useState(false);
  const [perm, setPerm] = useState<NotificationPermission | "unsupported">(() =>
    typeof window === "undefined" || !("Notification" in window) ? "unsupported" : Notification.permission,
  );

  const all = useMemo(() => data?.alerts ?? [], [data]);
  const mine = useMemo(() => all.filter((a) => isWatched(a, ids)), [all, ids]);
  const warnings = useMemo(() => all.filter((a) => a.level === "warning"), [all]);
  const client = useIsClient();
  // the watch list lives in this browser: count it only after hydration
  const badge = !client ? 0 : ids.length ? mine.length : warnings.length;

  // one browser notification per data update, for watched areas, while the app is open
  useEffect(() => {
    if (!data || perm !== "granted" || !mine.length || notified === data.generated) return;
    const n = new Notification(`Burning Calendar: ${mine.length} alert${mine.length > 1 ? "s" : ""} for your areas`, {
      body: mine
        .slice(0, 3)
        .map((a) => `${a.name}: ${a.title}`)
        .join("\n"),
      tag: "burning-calendar-alerts",
    });
    n.onclick = () => {
      window.focus();
      router.push(areaHref(mine[0].areaId));
    };
    setNotified(data.generated);
  }, [data, perm, mine, notified, setNotified, router]);

  async function enable() {
    if (perm === "unsupported") return;
    setPerm(await Notification.requestPermission());
  }

  function go(a: AlertItem) {
    setOpen(false);
    router.push(areaHref(a.areaId));
  }

  return (
    <Popover open={open} onOpenChange={setOpen}>
      <PopoverTrigger
        render={
          <Button variant="ghost" size="icon" aria-label={`Alerts${badge ? ` (${badge})` : ""}`} className="relative" />
        }
      >
        {badge ? <BellRing /> : <Bell />}
        {badge > 0 && (
          <span className="absolute -top-0.5 -right-0.5 grid min-w-4 place-items-center rounded-full bg-red-600 px-1 text-[10px] font-semibold text-white">
            {badge > 99 ? "99+" : badge}
          </span>
        )}
      </PopoverTrigger>
      <PopoverContent align="end" className="w-[380px] p-0">
        <div className="border-b px-3 py-2.5">
          <div className="text-sm font-semibold">Fire alerts</div>
          <div className="text-[11px] text-muted-foreground">
            {data ? `From data to ${formatDay(data.lastDay)} · updated with every data update` : "No alerts file yet (made by the data export)."}
          </div>
        </div>
        <div className="max-h-[60vh] overflow-y-auto">
          <Group
            title={ids.length ? `Your watched areas (${mine.length})` : "Your watched areas"}
            empty={ids.length ? "Nothing unusual in your areas." : "Open an area and press “Watch” to get its alerts here."}
            items={mine}
            onPick={go}
          />
          <Group title={`Warnings (${warnings.length})`} empty="No warnings." items={warnings.slice(0, 25)} onPick={go} />
        </div>
        <div className="space-y-1.5 border-t px-3 py-2.5 text-[11px] text-muted-foreground">
          {perm === "granted" ? (
            <p>Browser notifications are on: you get one when a data update brings alerts for your areas, while this app is open.</p>
          ) : perm === "denied" ? (
            <p>Notifications are blocked in this browser&apos;s site settings.</p>
          ) : perm === "unsupported" ? (
            <p>This browser does not support notifications.</p>
          ) : (
            <Button size="xs" variant="outline" onClick={enable}>
              <Bell /> Turn on browser notifications
            </Button>
          )}
          <p>
            Rules: {Object.values(data?.rules ?? {}).join("; ")}. Watched areas are kept in this browser only.
          </p>
        </div>
      </PopoverContent>
    </Popover>
  );
}

function Group({ title, empty, items, onPick }: { title: string; empty: string; items: AlertItem[]; onPick: (a: AlertItem) => void }) {
  return (
    <section className="py-1.5">
      <h4 className="px-3 py-1 text-[11px] font-semibold tracking-wide text-muted-foreground uppercase">{title}</h4>
      {items.length === 0 ? (
        <p className="px-3 pb-2 text-xs text-muted-foreground">{empty}</p>
      ) : (
        <ul>
          {items.map((a, i) => {
            const Icon = KIND_ICON[a.kind] ?? Flame;
            return (
              <li key={`${a.areaId}-${a.kind}-${i}`}>
                <button type="button" onClick={() => onPick(a)} className="flex w-full gap-2.5 px-3 py-2 text-left hover:bg-muted/60">
                  <Icon className={cn("mt-0.5 size-4 shrink-0", a.level === "warning" ? "text-red-600" : "text-amber-500")} />
                  <span className="min-w-0">
                    <span className="flex items-center gap-1.5 text-sm font-medium">
                      <span className="truncate">{a.name}</span>
                      <span
                        className={cn(
                          "shrink-0 rounded px-1 text-[10px] font-semibold uppercase",
                          a.level === "warning" ? "bg-red-600/15 text-red-700 dark:text-red-400" : "bg-amber-500/15 text-amber-700 dark:text-amber-400",
                        )}
                      >
                        {a.level}
                      </span>
                    </span>
                    <span className="block text-xs">{a.title}</span>
                    <span className="block text-[11px] text-muted-foreground">{a.detail}</span>
                  </span>
                </button>
              </li>
            );
          })}
        </ul>
      )}
    </section>
  );
}
