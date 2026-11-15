"""Cleaned fire detections for the web app's "hotspots CSV" download (queried in the browser).

    web/public/detections/<iso>/<year>.parquet   one file per country and year, sorted by local date,
                                                  in small row groups so the browser (DuckDB-wasm) reads
                                                  only the dates it needs over HTTP range requests
    web/public/detections/index.json          rows per country and year

Columns: latitude, longitude, acq_date (UTC), acq_time (HHMM UTC), solar_date (local), satellite,
confidence, frp (MW), daynight, adm1, adm2. These are the detections after cleaning (confidence,
type, gas-flare mask), not converted between satellites.

    python scripts/export_points.py                     # every country
    python scripts/export_points.py --countries MYS
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd
import pyarrow as pa
import pyarrow.compute as pc
import pyarrow.dataset as ds
import pyarrow.parquet as pq

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

import data as D  # noqa: E402

OUT_SCHEMA = pa.schema([
    ("latitude", pa.float64()), ("longitude", pa.float64()), ("acq_date", pa.date32()), ("acq_time", pa.int16()),
    ("solar_date", pa.date32()), ("satellite", pa.string()), ("confidence", pa.string()), ("frp", pa.float32()),
    ("daynight", pa.string()), ("adm1", pa.string()), ("adm2", pa.string()),
])


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # kept outside web/public/data, which the data export replaces as a whole
    ap.add_argument("--out", type=Path, default=ROOT / "web" / "public" / "detections")
    ap.add_argument("--years", nargs="*", type=int, help="only these years (daily updates); default all")
    ap.add_argument("--countries", nargs="*")
    ap.add_argument("--row-group", type=int, default=20_000)
    args = ap.parse_args(argv)
    t0 = time.time()
    schema = pa.schema([(c, pa.type_for_alias(t) if t != "timestamp[ns]" else pa.timestamp("ns"))
                        for c, t in D.POINT_SCHEMA_COLS.items()])
    dset = ds.dataset(str(D.POINTS_DIR), format="parquet", schema=schema)
    cube = D.get_cube()
    isos = sorted(args.countries or [c for c in cube["country"].unique() if c in D.COUNTRY_NAMES])
    index_path = args.out / "index.json"
    index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
    total = 0
    counts: dict[str, dict[str, int]] = {}
    wanted = set(isos)
    for year in (args.years or range(2000, pd.Timestamp.today().year + 1)):
        # one scan per year for all countries (scanning per country and year was ~40x slower)
        lo = pa.scalar(pd.Timestamp(year, 1, 1), pa.timestamp("ns"))
        hi = pa.scalar(pd.Timestamp(year + 1, 1, 1), pa.timestamp("ns"))
        t = dset.to_table(columns=[*OUT_SCHEMA.names, "country"],
                          filter=(pc.field("solar_date") >= lo) & (pc.field("solar_date") < hi)
                          & pc.field("country").isin(list(wanted)))
        if t.num_rows == 0:
            continue
        for iso in pc.unique(t.column("country")).to_pylist():
            sub = t.filter(pc.field("country") == iso).drop_columns(["country"])
            sub = sub.sort_by([("solar_date", "ascending"), ("satellite", "ascending")]).cast(OUT_SCHEMA, safe=False)
            d = args.out / iso.lower()
            d.mkdir(parents=True, exist_ok=True)
            pq.write_table(sub, d / f"{year}.parquet", row_group_size=args.row_group, compression="zstd",
                           use_dictionary=["satellite", "confidence", "daynight", "adm1", "adm2"],
                           write_statistics=True)
            counts.setdefault(iso.lower(), {})[str(year)] = sub.num_rows
            total += sub.num_rows
        print(f"{year}: {t.num_rows:,} detections, {time.time() - t0:,.0f} s", flush=True)
        del t
    for iso, ys in counts.items():
        index.setdefault(iso, {}).update(ys)
    args.out.mkdir(parents=True, exist_ok=True)
    index_path.write_text(json.dumps(index), encoding="utf-8")
    size = sum(f.stat().st_size for f in args.out.rglob("*.parquet")) / 1e6
    print(f"wrote {total:,} detections, {size:,.0f} MB in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
