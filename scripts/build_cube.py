"""Process all raw FIRMS files into data/processed/ (one file at a time, low memory).

    python scripts/build_cube.py                     # data/raw -> data/processed
    python scripts/build_cube.py --no-points         # skip per-hotspot Parquet (saves disk)

Re-running only processes new or changed files. Then harmonize any region:
    python scripts/run_pipeline.py --cube data/processed/cube.parquet --country MYS
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from burncal.config import Settings  # noqa: E402
from burncal.cube import build_cube, platform_coverage  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed")
    ap.add_argument("--no-points", action="store_true")
    ap.add_argument("--static-mask", type=Path, default=ROOT / "data" / "external" / "static_cells.parquet",
                    help="gas flare / industry mask from scripts/build_static_mask.py (used if the file exists)")
    ap.add_argument("--no-static-mask", action="store_true")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.WARNING)

    t0 = time.time()
    use_mask = not args.no_static_mask and args.static_mask.exists()
    print("static-source mask:", args.static_mask if use_mask else "none")
    s = Settings(static_mask=str(args.static_mask) if use_mask else None)
    cube = build_cube(args.raw, args.out, s, write_points=not args.no_points)
    print(f"cube: {len(cube):,} rows in {time.time() - t0:.0f}s -> {args.out / 'cube.parquet'}")
    if len(cube):
        print("platform coverage:", platform_coverage(cube))
        top = cube.groupby("country")["cell_days"].sum().sort_values(ascending=False)
        print("cell-days by country:\n" + top.to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
