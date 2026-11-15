import type { Ring } from "./own-area";

/** A circle of `radiusKm` around (lat, lon) as a lon/lat ring (local flat-earth, fine up to ~1,500 km). */
export function circleRing(lat: number, lon: number, radiusKm: number, n = 72): Ring {
  const dLat = radiusKm / 111.32;
  const dLon = radiusKm / (111.32 * Math.cos((lat * Math.PI) / 180));
  return Array.from({ length: n }, (_, i) => {
    const a = (2 * Math.PI * i) / n;
    return [lon + dLon * Math.cos(a), lat + dLat * Math.sin(a)] as [number, number];
  });
}

/** A latitude/longitude box as a ring. */
export function boxRing(west: number, south: number, east: number, north: number): Ring {
  if (!(east > west) || !(north > south)) throw new Error("East must be east of west and north north of south");
  return [
    [west, south],
    [east, south],
    [east, north],
    [west, north],
  ];
}
