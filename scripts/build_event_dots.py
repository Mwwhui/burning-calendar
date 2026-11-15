"""Where and when each listed fire event burned: its ~1 km NOAA-20 cell-days, for the map.

    python scripts/build_event_dots.py                    # events listed in web/public/data/events/*.json
    python scripts/build_event_dots.py --data web/public/data.next

Writes <data>/event-dots/<event id>.json (see burncal.events.dots_json). Only events that the
export lists (burning now / biggest this year / on record per area) get a file. Run after
scripts/export_web.py; one country's NOAA-20 detections are read at a time.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from burncal.events import EVENT_SATELLITE, cell_days, dots_json, event_cell_days, load_events  # noqa: E402


def listed_ids(data: Path) -> set[int]:
    ids: set[int] = set()
    for f in (data / "events").glob("*.json"):
        ids.update(int(e["id"]) for e in json.loads(f.read_text(encoding="utf-8"))["events"])
    return ids


def main(argv=None) -> int:
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.dataset as ds

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", type=Path, default=ROOT / "web" / "public" / "data")
    ap.add_argument("--processed", type=Path, default=ROOT / "data" / "processed")
    args = ap.parse_args(argv)
    t0 = time.time()

    ids = listed_ids(args.data)
    ev = load_events(args.processed / "events.parquet")
    ev = ev[ev["event_id"].isin(ids)]
    out = args.data / "event-dots"
    out.mkdir(parents=True, exist_ok=True)

    cols = {"latitude": pa.float64(), "longitude": pa.float64(), "solar_date": pa.timestamp("ns"),
            "satellite": pa.string(), "frp": pa.float64(), "country": pa.string()}
    dset = ds.dataset(str(args.processed / "points"), format="parquet", schema=pa.schema(list(cols.items())))
    written = missing = size = 0
    for i, (country, g) in enumerate(ev.groupby("country"), 1):
        f = ((pc.field("satellite") == EVENT_SATELLITE) & (pc.field("country") == country)
             & (pc.field("solar_date") >= pa.scalar(g["start"].min().to_pydatetime(), pa.timestamp("ns")))
             & (pc.field("solar_date") <= pa.scalar(g["end"].max().to_pydatetime(), pa.timestamp("ns"))))
        pts = dset.to_table(columns=["latitude", "longitude", "solar_date", "frp"], filter=f).to_pandas()
        cd = cell_days(pts)
        del pts
        for _, e in g.iterrows():
            cells = event_cell_days(cd, e)
            if cells.empty:
                missing += 1
                continue
            text = json.dumps(dots_json(cells, e["event_id"], e["start"]), separators=(",", ":"))
            (out / f"{int(e['event_id'])}.json").write_text(text, encoding="utf-8")
            written += 1
            size += len(text)
        print(f"\r{i} countries, {written:,} events", end="", flush=True)
    print(f"\n{written:,} event dot files ({size / 1e6:.1f} MB) -> {out}; {missing} not found"
          f" (events table older than the export?) in {time.time() - t0:.0f}s")
    return 0 if missing <= max(5, written // 100) else 1


if __name__ == "__main__":
    raise SystemExit(main())
