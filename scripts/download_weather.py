"""Daily weather for the forecast from NASA POWER (MERRA-2 based, no key needed).

One point per state/province (and Malaysian district), at the fire-weighted centre of the area's
VIIRS fire 2012+ (so weather is taken where it burns); points in the same 0.5 deg cell are merged.

    data/external/weather/points.parquet        area -> point (lat, lon), fire weight
    data/external/weather/power/<lat>_<lon>.json  cached daily series 2012-01-01..today
    data/external/weather/daily.parquet         point x date: rain, tmax, rh, wind, soil wetness

Variables: PRECTOTCORR (rain, mm/day), T2M_MAX (deg C), RH2M (%), WS2M (m/s), GWETTOP (topsoil
wetness 0-1). Source: NASA Langley POWER project, https://power.larc.nasa.gov (public, no copyright).

    python scripts/download_weather.py              # all areas (about 1-2 hours the first time; cached)
    python scripts/download_weather.py --refresh 30 # re-fetch the last 30 days only (daily updates)
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import requests

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

import data as D  # noqa: E402
from burncal.daily import load_daily  # noqa: E402

OUT = ROOT / "data" / "external" / "weather"
API = "https://power.larc.nasa.gov/api/temporal/daily/point"
PARAMS = ["PRECTOTCORR", "T2M_MAX", "RH2M", "WS2M", "GWETTOP"]
START = date(2012, 1, 1)
SNAP = 0.5  # merge points within one 0.5 deg cell (MERRA-2 is 0.5 x 0.625 deg)


def area_points() -> pd.DataFrame:
    """Fire-weighted centre per (country, adm1) and per Malaysian (country, adm1, adm2)."""
    rows = []
    countries = sorted(c for c in pd.read_parquet(D.DAILY_ADMIN, columns=["country"])["country"].dropna().unique()
                       if c in D.COUNTRY_NAMES)
    for c in countries:
        g = load_daily(D.DAILY_GRID, countries=[c])
        g = g[g["date"] >= pd.Timestamp(START)]
        if g.empty:
            continue
        g = g.assign(lat=(g["gy"].astype(float) + 0.5) * 0.1, lon=(g["gx"].astype(float) + 0.5) * 0.1)
        for keys in (["country", "adm1"], ["country", "adm1", "adm2"]):
            sub = g.dropna(subset=keys)
            if keys[-1] == "adm2":
                sub = sub[sub["country"] == "MYS"]
            if sub.empty:
                continue
            w = sub["cell_days"].astype(float)
            agg = sub.assign(wl=sub["lat"] * w, wo=sub["lon"] * w, w=w).groupby(keys, observed=True)[["wl", "wo", "w"]].sum()
            for k, r in agg.iterrows():
                k = k if isinstance(k, tuple) else (k,)
                rows.append({"country": k[0], "adm1": k[1], "adm2": k[2] if len(k) > 2 else None,
                             "lat": r["wl"] / r["w"], "lon": r["wo"] / r["w"], "weight": r["w"]})
        print(f"\r{c}: {len(rows)} area points", end="", flush=True)
    print()
    p = pd.DataFrame(rows)
    p["plat"] = (np.floor(p["lat"] / SNAP) + 0.5) * SNAP
    p["plon"] = (np.floor(p["lon"] / SNAP) + 0.5) * SNAP
    return p


def fetch(session: requests.Session, lat: float, lon: float, start: date, end: date) -> dict:
    params = {"parameters": ",".join(PARAMS), "community": "AG", "latitude": f"{lat:.2f}", "longitude": f"{lon:.2f}",
              "start": start.strftime("%Y%m%d"), "end": end.strftime("%Y%m%d"), "format": "JSON"}
    for attempt in range(5):
        try:
            r = session.get(API, params=params, timeout=120)
            if r.ok:
                return r.json()["properties"]["parameter"]
            if r.status_code in (429, 500, 502, 503, 504):
                time.sleep(10 * (attempt + 1))
                continue
            raise RuntimeError(f"POWER {r.status_code}: {r.text[:200]}")
        except requests.RequestException:
            time.sleep(10 * (attempt + 1))
    raise RuntimeError(f"POWER failed for {lat}, {lon}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--refresh", type=int, default=0, help="re-fetch the last N days for every cached point")
    ap.add_argument("--pause", type=float, default=0.3)
    args = ap.parse_args(argv)
    t0 = time.time()
    (OUT / "power").mkdir(parents=True, exist_ok=True)
    pts = area_points()
    pts.to_parquet(OUT / "points.parquet", index=False)
    uniq = pts[["plat", "plon"]].drop_duplicates().to_numpy()
    print(f"{len(pts)} areas -> {len(uniq)} weather points")
    end = date.today() - timedelta(days=1)
    session = requests.Session()
    session.headers["User-Agent"] = "burning-calendar (research; NASA POWER daily point)"
    for i, (lat, lon) in enumerate(uniq, 1):
        f = OUT / "power" / f"{lat:.2f}_{lon:.2f}.json"
        if f.exists():
            if not args.refresh:
                continue
            old = json.loads(f.read_text())
            new = fetch(session, lat, lon, end - timedelta(days=args.refresh), end)
            for k, v in new.items():
                old.setdefault(k, {}).update(v)
            f.write_text(json.dumps(old))
        else:
            f.write_text(json.dumps(fetch(session, lat, lon, START, end)))
        if i % 25 == 0 or i == len(uniq):
            print(f"{i}/{len(uniq)} points, {time.time() - t0:,.0f} s", flush=True)
        time.sleep(args.pause)
    # one long table point x date
    parts = []
    for lat, lon in uniq:
        f = OUT / "power" / f"{lat:.2f}_{lon:.2f}.json"
        if not f.exists():
            continue
        p = json.loads(f.read_text())
        df = pd.DataFrame({k: pd.Series(v) for k, v in p.items()})
        df.index = pd.to_datetime(df.index, format="%Y%m%d")
        df = df.replace(-999.0, np.nan)
        df["plat"], df["plon"] = lat, lon
        parts.append(df.rename_axis("date").reset_index())
    daily = pd.concat(parts, ignore_index=True).rename(columns={
        "PRECTOTCORR": "rain", "T2M_MAX": "tmax", "RH2M": "rh", "WS2M": "wind", "GWETTOP": "soil"})
    daily.to_parquet(OUT / "daily.parquet", index=False)
    print(f"wrote {len(daily):,} point-days ({daily['date'].min():%Y-%m-%d} to {daily['date'].max():%Y-%m-%d}) "
          f"in {time.time() - t0:,.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
