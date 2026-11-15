"""Build the static-source mask (gas flares, industry, volcanoes) from FIRMS archive labels.

    python scripts/build_static_mask.py                 # -> data/external/static_cells.parquet
    python scripts/build_static_mask.py --check 2025    # also test: mask from earlier years only

Reads the `type` column of every VIIRS archive (SP) CSV under data/raw. Then rebuild:
    python scripts/build_cube.py --out data/processed_new   (uses the mask if it exists)
See burncal.static for the method and the held-out test results.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from burncal.cube import raw_files  # noqa: E402
from burncal.static import in_mask, label_counts, static_cells  # noqa: E402

COLS = ["latitude", "longitude", "acq_date", "type", "instrument", "confidence"]


def viirs_labelled(raw: Path):
    """VIIRS SP rows with a type label and nominal/high confidence, one file at a time."""
    for p in raw_files(raw):
        if p.suffix == ".parquet":  # slim store (burncal.rawstore): standard schema
            d = pd.read_parquet(p, columns=["latitude", "longitude", "acq_date", "type", "sensor", "confidence", "product"])
            d = d[d["sensor"].astype(str).eq("VIIRS") & d["product"].astype(str).eq("SP") & d["type"].notna()
                  & d["confidence"].astype(str).isin(["n", "h", "nominal", "high"])]
            if len(d):
                yield d[["latitude", "longitude", "acq_date", "type"]].assign(acq_date=lambda x: x["acq_date"].dt.strftime("%Y-%m-%d"))
            continue
        head = pd.read_csv(p, nrows=0).columns
        if "type" not in head or "instrument" not in head:
            continue
        d = pd.read_csv(p, usecols=COLS)
        d = d[d["instrument"].astype(str).str.upper().eq("VIIRS")
              & d["confidence"].astype(str).str.lower().isin(["n", "h", "nominal", "high"])]
        if len(d):
            yield d[["latitude", "longitude", "acq_date", "type"]]


def check(frames: list[pd.DataFrame], year: int, min_labels: int, grid_deg: float) -> None:
    """Mask from years before `year`, applied to `year` as if it had no labels."""
    a = pd.concat(frames, ignore_index=True)
    yr = pd.to_datetime(a["acq_date"]).dt.year
    mask = static_cells(label_counts([a[yr < year]], grid_deg), min_labels)
    te = a[yr == year]
    # only test where the archive has data (the API box also covers neighbouring countries)
    tile = lambda d: (d["latitude"] // 0.25).astype(int) * 10000 + (d["longitude"] // 0.25).astype(int)  # noqa: E731
    te = te[tile(te).isin(set(tile(a[yr < year])))]
    hit = in_mask(te, mask, grid_deg)
    st = te["type"].astype(int).isin([1, 2, 3]).to_numpy()
    print(f"check {year}: {st.sum():,} labelled static detections, {(~st).sum():,} vegetation fires; "
          f"caught {(hit & st).sum() / max(st.sum(), 1):.1%}, vegetation fires removed "
          f"{(hit & ~st).sum() / max((~st).sum(), 1):.2%}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "external" / "static_cells.parquet")
    ap.add_argument("--min-labels", type=int, default=1)
    ap.add_argument("--grid-deg", type=float, default=0.01)
    ap.add_argument("--check", type=int, nargs="*", default=[])
    args = ap.parse_args(argv)
    t0 = time.time()
    frames = list(viirs_labelled(args.raw))
    counts = label_counts(frames, args.grid_deg)
    mask = static_cells(counts, args.min_labels)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    mask.to_parquet(args.out, index=False)
    print(f"{len(mask):,} static cells (>= {args.min_labels} labelled detections) of {len(counts):,} cells with "
          f"any static label -> {args.out} in {time.time() - t0:.0f}s")
    for y in args.check:
        check(frames, y, args.min_labels, args.grid_deg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
