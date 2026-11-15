"""Group NOAA-20 detections into fire events (for "how does the current fire compare?").

    python scripts/build_events.py        # data/processed/points -> data/processed/events.parquet

Run after scripts/build_cube.py. See burncal.events for the grouping rule.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from burncal.events import build_events  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--processed", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--peat", type=Path, default=ROOT / "data" / "external" / "peat_cells.parquet")
    ap.add_argument("--gap-days", type=int, default=5)
    args = ap.parse_args(argv)
    t0 = time.time()
    peat = pd.read_parquet(args.peat) if args.peat.exists() else None
    out = args.processed / "events.parquet"
    ev = build_events(args.processed / "points", out, peat_cells=peat, gap_days=args.gap_days)
    big = ev[ev["area_km2"] >= 10]
    print(f"{len(ev):,} events ({len(big):,} of 10 km2 or more) from {ev['start'].min():%d %b %Y} to "
          f"{ev['end'].max():%d %b %Y} -> {out} in {time.time() - t0:.0f}s")
    print(ev.nlargest(5, "area_km2")[["start", "end", "days", "area_km2", "country", "adm1"]].to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
