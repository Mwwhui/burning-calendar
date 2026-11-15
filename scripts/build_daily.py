"""Build the daily tables used for date ranges and user-drawn areas.

    python scripts/build_daily.py            # data/processed/points -> data/processed/daily_*.parquet

Run after scripts/build_cube.py (it reads the cleaned points the cube build writes).
Takes a few minutes for the full Southeast Asia record. See burncal.daily for details.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from burncal.daily import build_daily, build_detail  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--points", type=Path, default=ROOT / "data" / "processed" / "points")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--peat", type=Path, default=ROOT / "data" / "external" / "peat_cells.parquet",
                    help="peat share per 1 km cell (scripts/download_context.py --peat); used if it exists")
    ap.add_argument("--cache", type=Path, default=ROOT / "data" / "processed" / "daily_parts",
                    help="per-file parts, reused while a points file is unchanged (daily updates)")
    ap.add_argument("--no-detail", action="store_true", help="skip detail_admin (satellite differences, 2019-20)")
    args = ap.parse_args(argv)
    t0 = time.time()
    peat = pd.read_parquet(args.peat) if args.peat.exists() else None
    print("peat split:", args.peat if peat is not None else "none")
    pa, pg = build_daily(args.points, args.out, peat_cells=peat, cache_dir=args.cache)
    print(f"wrote {pa} ({pa.stat().st_size / 1e6:.1f} MB) and {pg} ({pg.stat().st_size / 1e6:.1f} MB) "
          f"in {time.time() - t0:.0f}s")
    if not args.no_detail:
        print("wrote", build_detail(args.points, args.out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
