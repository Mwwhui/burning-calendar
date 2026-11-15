"use client";

import { Crosshair } from "lucide-react";
import { useState } from "react";

import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogDescription, DialogHeader, DialogTitle } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { ToggleGroup, ToggleGroupItem } from "@/components/ui/toggle-group";
import { useCurrentArea } from "@/features/explorer/hooks/use-area";
import { useExplorer } from "@/features/explorer/store";
import { boxRing, circleRing } from "@/lib/analytics/shapes";
import { countryOf } from "@/lib/area";

type Kind = "circle" | "box";

function Field({ label, value, onChange }: { label: string; value: string; onChange: (v: string) => void }) {
  return (
    <label className="space-y-1 text-xs text-muted-foreground">
      {label}
      <Input inputMode="decimal" value={value} onChange={(e) => onChange(e.target.value)} className="h-8" />
    </label>
  );
}

/** Own area from coordinates: a circle (centre + radius) or a latitude/longitude box. */
export function CoordsDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { lookup, id } = useCurrentArea();
  const setOwnArea = useExplorer((s) => s.setOwnArea);
  const [kind, setKind] = useState<Kind>("circle");
  const [c, setC] = useState({ lat: "3.0", lon: "101.5", r: "25" });
  const [b, setB] = useState({ n: "3.5", s: "2.5", w: "101.0", e: "102.0" });
  const [error, setError] = useState<string | null>(null);

  function use() {
    const countryId = lookup ? countryOf(lookup, id) : undefined;
    if (!countryId) return setError("Open a country first: drawn areas use that country's data.");
    try {
      if (kind === "circle") {
        const [lat, lon, r] = [Number(c.lat), Number(c.lon), Number(c.r)];
        if (![lat, lon, r].every(Number.isFinite) || r <= 0 || r > 1500) throw new Error("Enter a centre and a radius of 1–1,500 km");
        setOwnArea({ ring: circleRing(lat, lon, r), countryId, label: `${r} km around ${lat.toFixed(3)}°, ${lon.toFixed(3)}°` });
      } else {
        const ring = boxRing(Number(b.w), Number(b.s), Number(b.e), Number(b.n));
        setOwnArea({ ring, countryId, label: `Box ${Number(b.s).toFixed(2)}° to ${Number(b.n).toFixed(2)}°N, ${Number(b.w).toFixed(2)}° to ${Number(b.e).toFixed(2)}°E` });
      }
      setError(null);
      onOpenChange(false);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-sm">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Crosshair className="size-4" /> Area from coordinates
          </DialogTitle>
          <DialogDescription>Latitude °N (south is negative), longitude °E.</DialogDescription>
        </DialogHeader>
        <ToggleGroup size="sm" variant="outline" spacing={0} value={[kind]} onValueChange={(v) => v[0] && setKind(v[0] as Kind)}>
          <ToggleGroupItem value="circle" className="px-3">Circle</ToggleGroupItem>
          <ToggleGroupItem value="box" className="px-3">Box</ToggleGroupItem>
        </ToggleGroup>
        {kind === "circle" ? (
          <div className="grid grid-cols-3 gap-2">
            <Field label="Centre lat" value={c.lat} onChange={(v) => setC({ ...c, lat: v })} />
            <Field label="Centre lon" value={c.lon} onChange={(v) => setC({ ...c, lon: v })} />
            <Field label="Radius km" value={c.r} onChange={(v) => setC({ ...c, r: v })} />
          </div>
        ) : (
          <div className="grid grid-cols-2 gap-2">
            <Field label="North" value={b.n} onChange={(v) => setB({ ...b, n: v })} />
            <Field label="South" value={b.s} onChange={(v) => setB({ ...b, s: v })} />
            <Field label="West" value={b.w} onChange={(v) => setB({ ...b, w: v })} />
            <Field label="East" value={b.e} onChange={(v) => setB({ ...b, e: v })} />
          </div>
        )}
        {error && <p className="text-xs text-destructive">{error}</p>}
        <Button onClick={use}>Use this area</Button>
      </DialogContent>
    </Dialog>
  );
}
