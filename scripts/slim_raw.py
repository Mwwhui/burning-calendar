"""Replace raw FIRMS CSVs by slim Parquet copies (burncal.rawstore) to save disk.

    python scripts/slim_raw.py --match Argentina           # only files whose path contains "Argentina"
    python scripts/slim_raw.py --dry-run                    # sizes only, nothing changed
    python scripts/slim_raw.py                              # every CSV under data/raw

Each copy is checked to read back identically before its CSV is deleted. A file that build_cube already
processed keeps its manifest entry (moved to the Parquet name), so it is not processed or counted again.
Run it while no other pipeline step is running.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from burncal.cube import raw_files  # noqa: E402
from burncal.rawstore import migrate_manifest, slim_file  # noqa: E402


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raw", type=Path, default=ROOT / "data" / "raw")
    ap.add_argument("--processed", type=Path, default=ROOT / "data" / "processed", help="build_cube store")
    ap.add_argument("--match", help="only files whose path contains this text")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args(argv)
    t0 = time.time()
    files = [p for p in raw_files(args.raw) if p.suffix == ".csv" and (not args.match or args.match in str(p))]
    before = sum(p.stat().st_size for p in files)
    print(f"{len(files)} CSV files, {before / 1e9:.2f} GB")
    if args.dry_run:
        return 0
    after, moved, skipped = 0, 0, 0
    for i, p in enumerate(files, 1):
        out = slim_file(p)
        if out is None:
            skipped += 1
            continue
        after += out.stat().st_size
        moved += migrate_manifest(args.processed, args.raw, p)
        print(f"\r{i}/{len(files)} files ({p.name})          ", end="", flush=True)
    print(f"\n{before / 1e9:.2f} GB -> {after / 1e9:.2f} GB; {moved} manifest entries moved, {skipped} not FIRMS "
          f"(kept); {time.time() - t0:.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
