"""Run the full pipeline and write outputs/.

    python scripts/run_pipeline.py --demo                 # synthetic data (NOT findings)
    python scripts/run_pipeline.py --data data/raw --bbox 99.5,0.8,119.5,7.5
"""

from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from burncal.config import Settings  # noqa: E402
from burncal.io import load_firms_folder, make_demo_data  # noqa: E402
from burncal.pipeline import run, write_outputs  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--demo", action="store_true", help="use synthetic demo data")
    src.add_argument("--data", type=Path, help="folder with FIRMS CSVs (small areas; loads everything in memory)")
    src.add_argument("--cube", type=Path, help="cube.parquet from scripts/build_cube.py (any size; country "
                                               "defaults to all of Southeast Asia)")
    ap.add_argument("--bbox", help="west,south,east,north")
    ap.add_argument("--country", help="ISO3 inside the real border, e.g. MYS (needs scripts/download_context.py)")
    ap.add_argument("--adm1", nargs="+", help="state(s)/province(s), e.g. Sarawak Sabah, or Riau")
    ap.add_argument("--adm2", nargs="+", help="Malaysian district(s)")
    ap.add_argument("--unit", choices=["cell_days", "points"], default="cell_days")
    ap.add_argument("--out", type=Path, default=ROOT / "outputs")
    ap.add_argument("--hotspots", action="store_true", help="also write clean_hotspots.csv")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    s = Settings(unit=args.unit)
    if args.bbox:
        s.bbox = tuple(float(v) for v in args.bbox.split(","))
    s.country, s.adm1, s.adm2 = args.country, args.adm1, args.adm2
    if args.cube:
        from burncal.cube import load_cube
        from burncal.pipeline import run_cube
        res = run_cube(load_cube(args.cube), s)
        print(f"Region: country={s.country or 'all Southeast Asia'} adm1={s.adm1} adm2={s.adm2}")
    else:
        raw = make_demo_data() if args.demo else load_firms_folder(args.data)
        res = run(raw, s)

    print("\nHarmonization steps")
    for st in res.harmonization.steps:
        extra = f"method={st.method} pairs={st.n_pairs} filled={st.months_filled} " \
                f"drift={st.drift.get('slope_log_per_year', float('nan')):+.3f} log/yr" if st.status == "applied" else st.reason
        print(f"  {st.donor:7s} {st.status:8s} {extra}")
        if st.selection:
            print(f"  {'':7s} {'':8s} why: {st.selection}")
    print("\nSeam tests (harmonized)\n", res.seams.round(3).to_string(index=False))
    print("\nSeam test (naive record)\n", res.naive_seams.round(3).to_string(index=False))
    for p in write_outputs(res, args.out, write_hotspots=args.hotspots):
        print("wrote", p)
    if args.demo:
        print("\nNOTE: demo data is synthetic. Never present these numbers as findings.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
