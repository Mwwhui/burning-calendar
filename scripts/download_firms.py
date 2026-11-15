"""Download NASA FIRMS hotspots for a bounding box through the FIRMS area API.

    python scripts/download_firms.py --source MODIS_SP VIIRS_NOAA20_SP \
        --start 2018-01-01 --end 2018-12-31

The MAP_KEY is read from the FIRMS_MAP_KEY environment variable or a .env file
(get one free at https://firms.modaps.eosdis.nasa.gov/api/map_key/).

How it works
- Checks /api/data_availability first and clamps the date range to what exists.
- The area API returns at most DAY_RANGE days per request, so the range is split into
  chunks. Each chunk is cached in <out>/.cache/<SOURCE>/ so an interrupted run resumes.
- Chunks are merged into <out>/<SOURCE>_<year>.csv, which burncal.io.load_firms_folder
  reads (it skips the hidden .cache folder).

For the full 2000-present history the FIRMS archive download page
(https://firms.modaps.eosdis.nasa.gov/download/) is faster: one request per sensor.
Use this script for automation and for keeping the current season up to date.
Suomi NPP stopped delivering data on 2 Nov 2026; use NOAA-20/NOAA-21 for recent months.
"""

from __future__ import annotations

import argparse
import io
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

API = "https://firms.modaps.eosdis.nasa.gov/api"
MALAYSIA_BBOX = "99.5,0.8,119.5,7.5"
# Southeast Asia: Myanmar to Papua, northern Myanmar to Timor. Also catches edges of
# NE India, Bangladesh, southern China, Papua New Guinea; regions.py tags countries.
SEA_BBOX = "92,-11.2,141.1,28.6"
# Rest of Asia as two boxes that do not overlap the "sea" box (92-141.1E, 11.2S-28.6N), so the
# 2026 files can be added next to the existing ones without counting a hotspot twice. A strip of
# 0.005 deg along the shared edges is left out on purpose (FIRMS boxes include their edges).
ASIA_WEST_BBOX = "25,-11.2,91.995,82"    # Middle East, Central Asia, South Asia, western Russia
ASIA_NORTH_BBOX = "92,28.605,180,82"     # China north of 28.6N, Mongolia, Korea, Japan, eastern Russia
# Argentina (with edges of Chile, Bolivia, Paraguay, Brazil, Uruguay; regions.py tags countries)
ARGENTINA_BBOX = "-73.6,-55.2,-53.5,-21.7"
BBOX_PRESETS = {"malaysia": MALAYSIA_BBOX, "sea": SEA_BBOX, "asia_west": ASIA_WEST_BBOX,
                "asia_north": ASIA_NORTH_BBOX, "argentina": ARGENTINA_BBOX}
KNOWN_SOURCES = [
    "MODIS_SP", "MODIS_NRT", "VIIRS_SNPP_SP", "VIIRS_SNPP_NRT",
    "VIIRS_NOAA20_SP", "VIIRS_NOAA20_NRT", "VIIRS_NOAA21_SP", "VIIRS_NOAA21_NRT",
]


def read_map_key() -> str:
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        env = Path(".env")
        if env.exists():
            for line in env.read_text().splitlines():
                if line.strip().startswith("FIRMS_MAP_KEY="):
                    os.environ.setdefault("FIRMS_MAP_KEY", line.split("=", 1)[1].strip().strip('"'))
    key = os.environ.get("FIRMS_MAP_KEY", "").strip()
    if not key:
        sys.exit("Set FIRMS_MAP_KEY in the environment or in .env")
    return key


def chunks(start: date, end: date, day_range: int):
    """Yield (chunk_start, n_days) covering start..end inclusive."""
    if day_range < 1:
        raise ValueError("day_range must be >= 1")
    d = start
    while d <= end:
        n = min(day_range, (end - d).days + 1)
        yield d, n
        d += timedelta(days=n)


def looks_like_csv(text: str) -> bool:
    return text.lstrip().lower().startswith("latitude")


def get(session, url: str, retries: int = 6) -> str:
    """GET with retries on rate-limit/server errors and dropped connections."""
    import requests

    for attempt in range(retries):
        try:
            r = session.get(url, timeout=120)
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            wait = min(30 * 2**attempt, 600)
            print(f"\n  connection problem ({type(e).__name__}), retrying in {wait}s")
            time.sleep(wait)
            continue
        if r.status_code == 200:
            return r.text
        if r.status_code in (429, 500, 502, 503, 504):
            wait = min(30 * 2**attempt, 600)
            print(f"\n  HTTP {r.status_code}, retrying in {wait}s")
            time.sleep(wait)
            continue
        r.raise_for_status()
    raise RuntimeError(f"Failed after {retries} attempts: {url.split('/csv/')[0]}/...")


def key_usage(session, key: str) -> tuple[int, int]:
    """(current_transactions, transaction_limit) for the MAP_KEY in the current 10-minute window."""
    import json

    text = get(session, f"https://firms.modaps.eosdis.nasa.gov/mapserver/mapkey_status/?MAP_KEY={key}")
    d = json.loads(text)
    return int(d.get("current_transactions", 0)), int(d.get("transaction_limit", 5000))


def wait_for_budget(session, key: str, max_share: float = 0.7) -> None:
    """Sleep until the key uses less than `max_share` of its 10-minute transaction limit.

    Each area request costs several transactions (~2 per day requested), so a fixed
    pause is not enough; dropping below the limit avoids FIRMS resetting connections.
    """
    while True:
        used, limit = key_usage(session, key)
        if used < max_share * limit:
            return
        print(f"\n  {used}/{limit} transactions used in this 10-minute window, pausing 60s")
        time.sleep(60)


def availability(session, key: str) -> pd.DataFrame:
    text = get(session, f"{API}/data_availability/csv/{key}/all")
    return pd.read_csv(io.StringIO(text))


def download_source(session, key, source, bbox, start, end, day_range, out: Path, pause: float) -> list[Path]:
    tag = bbox_tag(bbox)
    cache = out / ".cache" / tag / source
    cache.mkdir(parents=True, exist_ok=True)
    plan = list(chunks(start, end, day_range))
    fetched = 0
    for i, (d, n) in enumerate(plan, 1):
        f = cache / f"{d.isoformat()}_{n}.csv"
        if f.exists():
            continue
        if fetched % 25 == 0:
            wait_for_budget(session, key)
        fetched += 1
        text = get(session, f"{API}/area/csv/{key}/{source}/{bbox}/{n}/{d.isoformat()}")
        if not looks_like_csv(text):
            raise RuntimeError(f"{source} {d}: FIRMS returned an error: {text[:200]!r}")
        f.write_text(text, encoding="utf-8")
        print(f"\r{source}: {i}/{len(plan)} chunks", end="", flush=True)
        time.sleep(pause)
    print()
    # merge chunks into one file per (chunk start) year, one year at a time to limit memory
    dest = out / "api" / tag
    dest.mkdir(parents=True, exist_ok=True)
    by_year: dict[str, list[Path]] = {}
    for f in sorted(cache.glob("*.csv")):
        if f.stat().st_size > 0:
            by_year.setdefault(f.name[:4], []).append(f)
    written = []
    for year, files in sorted(by_year.items()):
        # stream chunk files to disk line by line (chunks never overlap in dates), so memory
        # stays flat even for Southeast Asia-sized years (millions of rows)
        p = dest / f"{source}_{year}.csv"
        tmp = p.with_suffix(".csv.part")
        header, rows = None, 0
        with open(tmp, "w", encoding="utf-8", newline="") as out_fh:
            for f in files:
                with open(f, encoding="utf-8") as in_fh:
                    first = in_fh.readline()
                    if not first.strip():
                        continue
                    if header is None:
                        header = first
                        out_fh.write(header)
                    elif first != header:
                        raise RuntimeError(f"{f.name}: columns differ from other chunks")
                    for line in in_fh:
                        if line.strip():
                            # FIRMS chunks often lack a final newline; without this the
                            # last row of one chunk would be glued to the next chunk's first
                            out_fh.write(line if line.endswith("\n") else line + "\n")
                            rows += 1
        if rows:
            tmp.replace(p)
            written.append(p)
        else:
            tmp.unlink()
    if not written:
        print(f"{source}: no detections")
    return written


def bbox_tag(bbox: str) -> str:
    """Folder-safe name for a bbox string, so caches of different areas never mix."""
    return "bbox_" + "_".join(f"{float(v):g}" for v in bbox.split(","))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", nargs="+", required=True, help=" ".join(KNOWN_SOURCES))
    ap.add_argument("--bbox", default="sea",
                    help="west,south,east,north, or a preset: " + ", ".join(BBOX_PRESETS) + " (default: sea)")
    ap.add_argument("--start", required=True, type=date.fromisoformat)
    ap.add_argument("--end", required=True, type=date.fromisoformat)
    ap.add_argument("--day-range", type=int, default=5, help="days per request (FIRMS limit; default 5)")
    ap.add_argument("--out", type=Path, default=Path("data/raw"))
    ap.add_argument("--pause", type=float, default=1.0, help="seconds between requests")
    args = ap.parse_args(argv)
    args.bbox = BBOX_PRESETS.get(args.bbox, args.bbox)

    import requests

    key = read_map_key()
    session = requests.Session()
    avail = availability(session, key)
    for source in args.source:
        row = avail[avail["data_id"] == source]
        if row.empty:
            print(f"{source}: not listed by FIRMS data_availability, skipping")
            continue
        lo = date.fromisoformat(str(row["min_date"].iloc[0]))
        hi = date.fromisoformat(str(row["max_date"].iloc[0]))
        start, end = max(args.start, lo), min(args.end, hi)
        if start > end:
            print(f"{source}: available {lo}..{hi}, outside requested range")
            continue
        print(f"{source}: downloading {start}..{end}")
        for p in download_source(session, key, source, args.bbox, start, end, args.day_range, args.out, args.pause):
            print("  wrote", p)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
