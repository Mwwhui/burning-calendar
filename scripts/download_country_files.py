"""Download FIRMS per-country yearly hotspot files (no MAP_KEY needed).

    python scripts/download_country_files.py                 # all of Southeast Asia
    python scripts/download_country_files.py --region asia   # every Asian country with a FIRMS file
    python scripts/download_country_files.py --countries Malaysia --sensors modis

Files: https://firms.modaps.eosdis.nasa.gov/data/country/<sensor>/<year>/<sensor>_<year>_<Country>.csv
- sensors: modis (2000-), viirs-snpp (2012-), viirs-jpss1 (= NOAA-20, 2018-)
- NOAA-21 has no country files and the current year has none until it is complete:
  get those with scripts/download_firms.py (area API, needs MAP_KEY).
- FIRMS assigns each hotspot to a country; files are complete standard (SP) data.

Saved to data/raw/country/<sensor>/<sensor>_<year>_<Country>.csv. Downloads go to a
.part file first and are renamed when complete, so an interrupted run resumes cleanly.
A missing file (404) is recorded in data/raw/country/missing.txt and skipped next time.
"""

from __future__ import annotations

import argparse
import time
from pathlib import Path

import requests

BASE = "https://firms.modaps.eosdis.nasa.gov/data/country"
# FIRMS file names for Southeast Asian countries (checked 2026-11-11)
SEA_COUNTRIES = [
    "Brunei_Darussalam", "Cambodia", "Indonesia", "Lao_PDR", "Malaysia", "Myanmar",
    "Philippines", "Singapore", "Thailand", "Timor-Leste", "Vietnam",
]
# Rest of Asia (FIRMS spellings checked 2026-11-12 with HEAD requests on modis_2020_*). Russia is
# one file for the whole country (European part included). North Korea has no country file under
# any spelling tried, so its 2000-2025 history is missing; Macao has none either.
OTHER_ASIA_COUNTRIES = [
    "Afghanistan", "Armenia", "Azerbaijan", "Bahrain", "Bangladesh", "Bhutan", "China", "Cyprus", "Georgia",
    "Hong_Kong", "India", "Iran", "Iraq", "Israel", "Japan", "Jordan", "Kazakhstan", "Kuwait", "Kyrgyzstan",
    "Lebanon", "Maldives", "Mongolia", "Nepal", "Oman", "Pakistan", "Palestine", "Qatar", "Republic_of_Korea",
    "Russian_Federation", "Saudi_Arabia", "Sri_Lanka", "Syria", "Taiwan", "Tajikistan", "Turkey", "Turkmenistan",
    "United_Arab_Emirates", "Uzbekistan", "Yemen",
]
REGIONS = {"sea": SEA_COUNTRIES, "asia": SEA_COUNTRIES + OTHER_ASIA_COUNTRIES}
SENSOR_YEARS = {"modis": 2000, "viirs-snpp": 2012, "viirs-jpss1": 2018}
LAST_COMPLETE_YEAR = 2025


def download(session: requests.Session, url: str, dest: Path, retries: int = 5) -> str:
    """Return 'ok', 'exists' or 'missing'."""
    if dest.exists():
        return "exists"
    part = dest.with_suffix(dest.suffix + ".part")
    for attempt in range(retries):
        try:
            with session.get(url, stream=True, timeout=300) as r:
                if r.status_code == 404:
                    return "missing"
                r.raise_for_status()
                dest.parent.mkdir(parents=True, exist_ok=True)
                with open(part, "wb") as fh:
                    for chunk in r.iter_content(1 << 20):
                        fh.write(chunk)
            part.replace(dest)
            return "ok"
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout,
                requests.exceptions.ChunkedEncodingError, requests.exceptions.HTTPError) as e:
            wait = min(15 * 2**attempt, 300)
            print(f"\n  {dest.name}: {type(e).__name__}, retry in {wait}s")
            time.sleep(wait)
    raise RuntimeError(f"Failed: {url}")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--countries", nargs="+", default=None, help="FIRMS country names (default: --region)")
    ap.add_argument("--region", choices=list(REGIONS), default="sea")
    ap.add_argument("--sensors", nargs="+", default=list(SENSOR_YEARS), choices=list(SENSOR_YEARS))
    ap.add_argument("--first-year", type=int, default=2000)
    ap.add_argument("--last-year", type=int, default=LAST_COMPLETE_YEAR)
    ap.add_argument("--out", type=Path, default=Path("data/raw/country"))
    args = ap.parse_args(argv)
    args.countries = args.countries or REGIONS[args.region]

    args.out.mkdir(parents=True, exist_ok=True)
    missing_log = args.out / "missing.txt"
    known_missing = set(missing_log.read_text().split()) if missing_log.exists() else set()

    jobs = [(s, y, c) for s in args.sensors
            for y in range(max(args.first_year, SENSOR_YEARS[s]), args.last_year + 1)
            for c in args.countries]
    session = requests.Session()
    counts = {"ok": 0, "exists": 0, "missing": 0}
    total_bytes = 0
    t0 = time.time()
    for i, (s, y, c) in enumerate(jobs, 1):
        name = f"{s}_{y}_{c}.csv"
        if name in known_missing:
            counts["missing"] += 1
            continue
        dest = args.out / s / name
        status = download(session, f"{BASE}/{s}/{y}/{name}", dest)
        counts[status] += 1
        if status == "missing":
            known_missing.add(name)
            with open(missing_log, "a") as fh:
                fh.write(name + "\n")
        elif status == "ok":
            total_bytes += dest.stat().st_size
        print(f"\r{i}/{len(jobs)} files | new {counts['ok']} ({total_bytes / 1e9:.2f} GB) "
              f"| already had {counts['exists']} | not on server {counts['missing']} "
              f"| {time.time() - t0:.0f}s   ", end="", flush=True)
    print("\ndone")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
