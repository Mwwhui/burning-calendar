"""Cleaned detection points -> fine playback cells and recent detections, per country.

    data/processed/fine_cells/<ISO>.parquet   cell-days per satellite, year, month, adm1, adm2, ~2 km cell,
                                              with detection position sums (burncal.fine.fine_table)
    data/processed/recent/<ISO>.parquet       the latest `--recent-days` days of detections
                                              (lat, lon, date, satellite, FRP, day/night)

Reads one country and one year at a time, so memory stays small.

    python scripts/build_fine_cells.py                 # every country in the cube
    python scripts/build_fine_cells.py --countries MYS
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

import data as D  # noqa: E402
from burncal.fine import fine_table  # noqa: E402

COLS = ["latitude", "longitude", "solar_date", "satellite", "adm1", "adm2", "frp", "daynight"]


def dataset(points_dir: Path) -> ds.Dataset:
    schema = pa.schema([(c, pa.type_for_alias(t) if t != "timestamp[ns]" else pa.timestamp("ns"))
                        for c, t in D.POINT_SCHEMA_COLS.items()])
    return ds.dataset(str(points_dir), format="parquet", schema=schema)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--points", type=Path, default=D.POINTS_DIR)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--countries", nargs="*")
    ap.add_argument("--recent-days", type=int, default=60)
    ap.add_argument("--years", nargs="*", type=int,
                    help="only recompute these years and keep the others (daily updates); default all")
    args = ap.parse_args(argv)
    t0 = time.time()
    dset = dataset(args.points)
    cube = D.get_cube()
    isos = sorted(args.countries or [c for c in cube["country"].unique() if c in D.COUNTRY_NAMES])
    # last complete day of data (as the app uses), so "recent" ends where the data ends
    from burncal import daily as DL
    admin, _ = D.get_daily()
    last = pd.Timestamp(DL.last_complete_day(DL.daily_for_region(admin, None))).normalize()
    del admin
    (args.out / "fine_cells").mkdir(parents=True, exist_ok=True)
    (args.out / "recent").mkdir(parents=True, exist_ok=True)
    recent_years = {last.year, (last - pd.Timedelta(days=args.recent_days)).year}
    for iso in isos:
        parts, recent = [], []
        target = (args.out / "fine_cells" / f"{iso}.parquet")
        if args.years and target.exists():
            old = pd.read_parquet(target)
            parts.append(old[~old["year"].isin(args.years)])
            todo = sorted(set(args.years) | recent_years)
        else:
            todo = list(range(2000, last.year + 1))
        for year in todo:
            flt = ((pc.field("country") == iso)
                   & (pc.field("solar_date") >= pa.scalar(pd.Timestamp(year, 1, 1), pa.timestamp("ns")))
                   & (pc.field("solar_date") < pa.scalar(pd.Timestamp(year + 1, 1, 1), pa.timestamp("ns"))))
            p = dset.to_table(columns=COLS, filter=flt).to_pandas()
            if p.empty:
                continue
            if not args.years or year in args.years or not target.exists():
                parts.append(fine_table(p))
            r = p[(p["solar_date"] > last - pd.Timedelta(days=args.recent_days)) & (p["solar_date"] <= last)]
            if len(r):
                recent.append(r)
        if not parts:
            continue
        f = pd.concat(parts, ignore_index=True)
        f.to_parquet(args.out / "fine_cells" / f"{iso}.parquet", index=False)
        if recent:
            r = pd.concat(recent, ignore_index=True)
            r[COLS].to_parquet(args.out / "recent" / f"{iso}.parquet", index=False)
        print(f"{iso}: {len(f):,} fine cells, {sum(len(x) for x in recent):,} recent detections, "
              f"{time.time() - t0:,.0f} s", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
