"use client";

import { useQuery } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, Cloud, Flame, X } from "lucide-react";

import { useExplorer, type SatPhoto } from "@/features/explorer/store";
import {
  CLEAR_MAX,
  clearestPerDay,
  dailyLayer,
  daysAround,
  detailLayers,
  DIST_FIRST,
  DIST_LEGEND,
  findDetailDays,
  pickPair,
  shiftDay,
  type DetailDay,
} from "@/lib/gibs";
import { formatDay } from "@/lib/format";
import { cn } from "@/lib/utils";

const GLASS = "rounded-lg border bg-background/88 shadow-md backdrop-blur-md";
const DAY_RE = / \d{4}$/;
const short = (d: string) => formatDay(d).replace(DAY_RE, "");

/** Yesterday (UTC): the newest day with a complete NOAA-20 picture over Asia. */
export function latestPhotoDay(): string {
  return shiftDay(new Date().toISOString().slice(0, 10), -1);
}

/** Controls of the satellite photo: which day and view, 30 m detail, vegetation loss, before / after a fire. */
export function PhotoBar() {
  const photo = useExplorer((s) => s.photo);
  const setPhoto = useExplorer((s) => s.setPhoto);
  if (!photo) return null;
  const max = latestPhotoDay();
  // typing in the date box passes through half-typed years: ignore days before the first daily photo
  const go = (date: string) => date >= "2000-02-24" && setPhoto({ ...photo, date: date > max ? max : date });
  const view = photo.view ?? "true";
  const hasDetail = view === "true" && detailLayers(photo.date).length > 0;
  const btn = "inline-flex h-6 items-center rounded-md px-1.5 text-xs hover:bg-muted disabled:opacity-40";
  const seg = (on: boolean) => cn("px-2 py-0.5", on ? "bg-foreground text-background" : "hover:bg-muted");

  return (
    <div className={cn(GLASS, "pointer-events-auto absolute top-12 left-3 z-10 max-h-[calc(100%-13rem)] w-[min(23rem,calc(100%-4.5rem))] overflow-y-auto p-2 text-xs")}>
      <div className="flex items-center justify-between gap-2">
        <span className="font-medium">
          Satellite photo · <span className="text-muted-foreground">{dailyLayer(photo.date).name}</span>
        </span>
        <button type="button" aria-label="Hide satellite photo" className={btn} onClick={() => setPhoto(null)}>
          <X className="size-3.5" />
        </button>
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-1">
        <button type="button" aria-label="Day before" className={cn(btn, "border")} onClick={() => go(shiftDay(photo.date, -1))}>
          <ChevronLeft className="size-3.5" />
        </button>
        <input
          type="date"
          aria-label="Day of the photo"
          value={photo.date}
          min="2000-02-24"
          max={max}
          onChange={(e) => e.target.value && go(e.target.value)}
          className="h-6 rounded-md border bg-background px-1.5 tabular-nums"
        />
        <button type="button" aria-label="Day after" disabled={photo.date >= max} className={cn(btn, "border")} onClick={() => go(shiftDay(photo.date, 1))}>
          <ChevronRight className="size-3.5" />
        </button>
        <label className="ml-auto inline-flex items-center gap-1" title="Hide the fire dots to see the ground">
          <input type="checkbox" checked={!photo.hideFire} onChange={(e) => setPhoto({ ...photo, hideFire: !e.target.checked })} />
          <Flame className="size-3 text-orange-500" /> fire
        </label>
      </div>

      <div className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1">
        <div className="inline-flex overflow-hidden rounded-md border" role="group" aria-label="Photo view">
          <button type="button" className={seg(view === "true")} onClick={() => setPhoto({ ...photo, view: "true" })}>
            Natural colour
          </button>
          <button
            type="button"
            className={cn(seg(view === "swir"), "border-l")}
            title="Short-wave infrared: sees through smoke (not cloud); burn scars red-brown, plants bright green"
            onClick={() => setPhoto({ ...photo, view: "swir" })}
          >
            Burn scars (through smoke)
          </button>
        </div>
        {hasDetail && (
          <label className="inline-flex items-center gap-1">
            <input type="checkbox" checked={photo.detail} onChange={(e) => setPhoto({ ...photo, detail: e.target.checked })} />
            30 m detail
          </label>
        )}
      </div>

      <label className={cn("mt-1.5 flex items-center gap-1", photo.date < DIST_FIRST && "opacity-50")}>
        <input
          type="checkbox"
          disabled={photo.date < DIST_FIRST}
          checked={!!photo.dist}
          onChange={(e) => setPhoto({ ...photo, dist: e.target.checked })}
        />
        Vegetation loss up to this day (30 m, NASA OPERA{photo.date < DIST_FIRST ? ", from 2023" : ""})
      </label>
      {photo.dist && photo.date >= DIST_FIRST && (
        <div className="mt-1 grid grid-cols-2 gap-x-2 gap-y-0.5 pl-5 text-[11px] text-muted-foreground">
          {DIST_LEGEND.map((l) => (
            <span key={l.rgb} className="flex items-center gap-1">
              <span className="inline-block size-2.5 shrink-0 rounded-sm" style={{ background: `rgb(${l.rgb})` }} />
              {l.label}
            </span>
          ))}
        </div>
      )}

      {photo.fire ? <FireDays photo={photo} /> : null}

      <p className="mt-1.5 leading-snug text-muted-foreground">
        {view === "true"
          ? "~250 m daily photo, early afternoon; zoom in for 30 m Landsat / Sentinel-2 on days one of them passed (blank otherwise). Clouds hide the ground: pick a clear day, use the burn-scar view through smoke, or vegetation loss, which combines every clear look."
          : "Short-wave infrared, ~250 m, so blurry when zoomed in: best for big fires and smoky regions. Smoke is nearly invisible, fresh burn scars are dark red-brown, plants bright green, clouds still white or cyan."}
      </p>
    </div>
  );
}

function cloudWord(c: number): string {
  return c <= 0.05 ? "clear" : c <= CLEAR_MAX ? "mostly clear" : c <= 0.6 ? "part cloud" : "cloudy";
}

/** Around a fire: the days with a 30 m picture over it, how cloudy each was, and the clearest before / after. */
function FireDays({ photo }: { photo: SatPhoto }) {
  const setPhoto = useExplorer((s) => s.setPhoto);
  const f = photo.fire!;
  const latest = latestPhotoDay();
  const { data, isLoading } = useQuery({
    queryKey: ["hls-days", f.lon, f.lat, f.start, f.end, latest],
    queryFn: () => findDetailDays(f.lon, f.lat, daysAround(f.start, f.end, latest)),
    staleTime: Infinity,
  });
  const [b30, a30] = data ? pickPair(data, f.start, f.end) : [null, null];
  const days = data ? clearestPerDay(data) : [];
  const open = (d: string, extra: Partial<SatPhoto> = {}) => setPhoto({ ...photo, view: "true", detail: true, ...extra, date: d > latest ? latest : d });

  const pairBtn = (d: DetailDay | null, fallback: string | undefined, label: string) => {
    const date = d?.date ?? fallback;
    if (!date) return null;
    return (
      <button
        type="button"
        onClick={() => open(date)}
        className={cn("rounded-md border px-2 py-0.5", photo.date === date && "border-foreground bg-foreground text-background")}
        title={d ? `${d.sat === "S" ? "Sentinel-2" : "Landsat"}, ${Math.round(d.cloud * 100)} % cloud` : "daily 250 m photo"}
      >
        {label} · {short(date)}
        {d && d.cloud > CLEAR_MAX && <Cloud className="ml-1 inline size-3" />}
      </button>
    );
  };

  return (
    <div className="mt-2 space-y-1 border-t pt-1.5">
      <div className="flex flex-wrap items-center gap-1">
        <span className="text-muted-foreground">
          This fire ({short(f.start)} – {short(f.end)}):
        </span>
        {pairBtn(b30, photo.pair?.[0], "Before")}
        {pairBtn(a30, photo.pair?.[1], "After")}
      </div>
      {!isLoading && (b30 || a30) && (
        <p className="text-[11px] text-muted-foreground">
          {b30 && a30
            ? `Clearest 30 m pictures nearest the fire: ${cloudWord(b30.cloud)} before, ${cloudWord(a30.cloud)} after.`
            : "A 30 m picture was found on one side only."}{" "}
          Turn on vegetation loss to see what changed even under cloud.
        </p>
      )}
      <div className="flex flex-wrap items-center gap-1">
        <span className="text-muted-foreground">30 m days:</span>
        {isLoading ? (
          <span className="text-muted-foreground">checking ±3 weeks for clear pictures…</span>
        ) : days.length ? (
          days.map((d) => (
            <button
              key={d.date}
              type="button"
              title={`${d.sat === "S" ? "Sentinel-2" : "Landsat"}: ${Math.round(d.cloud * 100)} % cloud (${cloudWord(d.cloud)})`}
              onClick={() => open(d.date)}
              className={cn(
                "rounded-md border px-1.5 py-0.5 tabular-nums",
                d.cloud > 0.6 && "border-dashed text-muted-foreground opacity-60",
                d.cloud <= CLEAR_MAX && "border-emerald-600/60",
                photo.date === d.date && "border-foreground bg-foreground text-background opacity-100",
              )}
            >
              {short(d.date)} <span className="opacity-70">{Math.round(d.cloud * 100)}%☁</span>
            </button>
          ))
        ) : (
          <span className="text-muted-foreground">none within 3 weeks; try the burn-scar view or vegetation loss</span>
        )}
      </div>
    </div>
  );
}
