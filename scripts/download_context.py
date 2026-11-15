"""Download context data into data/external/ (not committed; re-run to refresh).

    python scripts/download_context.py           # ONI, DMI, ASMC review links, boundaries
    python scripts/download_context.py --peat    # + CIFOR peat map (40 MB) -> peat_cells.parquet
    python scripts/download_context.py --gfed    # + GFED5 monthly burned area (265 MB) -> gfed5_regions.parquet

- NOAA CPC Oceanic Nino Index (ONI): https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt
- NOAA PSL Dipole Mode Index (IOD, HadISST): https://psl.noaa.gov/data/timeseries/month/DMI
- ASMC monthly "Review of Regional Haze Situation" links (RSS feed of the haze review category)
- CIFOR tropical peatland map v2.1 (Gumbricht et al. 2017, CC BY 4.0), needs py7zr + rasterio
- GFED5 burned area (Chen et al. 2023, CC BY 4.0, Zenodo 7668424), needs h5py
- geoBoundaries (gbOpen; licences vary by country, see geoBoundaries-meta.json) simplified GeoJSON:
    ADM0 + ADM1 for every Asian country (burncal.regions.ASIA_ISO3) and Argentina, MYS and ARG ADM2,
    ADM0 for non-Asian neighbours inside the download boxes
Files already present are skipped (delete them to refresh).
"""

from __future__ import annotations

import json
import time
import sys
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "external"
ONI_URL = "https://www.cpc.ncep.noaa.gov/data/indices/oni.ascii.txt"
DMI_URL = "https://psl.noaa.gov/data/timeseries/month/data/dmi.had.long.csv"
ASMC_FEED = "https://asmc.asean.org/category/haze-review/feed/?paged={page}"
PEAT_URL = "https://data.cifor-icraf.org/api/access/datafile/3261"  # TROP-SUBTROP_PeatV21_2016_CIFOR.7z
GFED_URL = "https://zenodo.org/records/7668424/files/BA.zip?download=1"
GB_API = "https://www.geoboundaries.org/api/current/{release}/{iso}/{level}/"
# Files taken from another geoBoundaries release than gbOpen. ARG gbOpen ADM1 (checked 2026-11-15) merges
# Entre Rios into Buenos Aires and has 23 units; gbHumanitarian (Instituto Geografico Nacional / UNHCR, 24 units)
# is correct, and ADM2 is taken from the same release so departments and provinces match.
GB_RELEASE = {("ARG", "ADM1"): "gbHumanitarian", ("ARG", "ADM2"): "gbHumanitarian"}
sys.path.insert(0, str(ROOT / "src"))
from burncal.regions import ASIA_ISO3, OTHER_ISO3  # noqa: E402

# Non-Asian countries inside the download boxes (25-180E, 11.2S-82N): tagged so their fires are not
# snapped into an Asian neighbour, then left out of every Asian total.
NEIGHBOURS = ["PNG", "UKR", "BLR", "FIN", "EST", "LVA", "LTU", "ROU", "MDA", "BGR", "GRC", "NOR", "EGY", "LBY",
              "SDN", "SSD", "ERI", "ETH", "DJI", "SOM", "KEN", "UGA", "TZA", "RWA", "BDI", "COD", "ZMB", "MWI", "MOZ"]
# Argentina's neighbours inside its download box (73.6-53.5 W, 55.2-21.7 S), same reason.
NEIGHBOURS_AMERICAS = ["CHL", "BOL", "PRY", "BRA", "URY"]
BOUNDARIES = ([(iso, "ADM0") for iso in list(ASIA_ISO3) + list(OTHER_ISO3) + NEIGHBOURS + NEIGHBOURS_AMERICAS]
              + [(iso, "ADM1") for iso in list(ASIA_ISO3) + list(OTHER_ISO3)]
              + [("MYS", "ADM2"), ("ARG", "ADM2")])


def fetch(url: str, retries: int = 5) -> requests.Response:
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=120, headers={"User-Agent": "curl/8.0"})
            r.raise_for_status()
            return r
        except (requests.exceptions.ConnectionError, requests.exceptions.Timeout) as e:
            if attempt == retries - 1:
                raise
            wait = 10 * 2**attempt
            print(f"  network problem ({type(e).__name__}), retry in {wait}s")
            time.sleep(wait)


def asmc_reviews() -> None:
    """Month -> ASMC haze review URL(s), from the RSS feed (newest first, 10 per page)."""
    import html
    import re

    import pandas as pd

    rows = []
    for page in range(1, 60):
        try:
            r = fetch(ASMC_FEED.format(page=page))
        except requests.exceptions.HTTPError as e:
            if e.response is not None and e.response.status_code == 404:  # past the last page
                break
            raise
        items = re.findall(r"<item>.*?<title>(.*?)</title>.*?<link>(.*?)</link>", r.text, re.S)
        if not items:
            break
        for title, link in items:
            title = html.unescape(title).strip()
            m = re.search(r"(January|February|March|April|May|June|July|August|September|October|November|"
                          r"December)\s+(\d{4})", title)
            if m:
                rows.append({"month": pd.Period(f"{m.group(2)}-{m.group(1)[:3]}", "M").strftime("%Y-%m"),
                             "title": title, "url": link.strip()})
    t = pd.DataFrame(rows).drop_duplicates("url").sort_values(["month", "title"])
    t.to_csv(OUT / "asmc_reviews.csv", index=False)
    print(f"wrote asmc_reviews.csv: {len(t)} reviews, {t['month'].min()} to {t['month'].max()}")


def peat() -> None:
    import py7zr

    sys.path.insert(0, str(ROOT / "src"))
    from burncal.peat import DEFAULT_PEAT_CELLS, DEFAULT_PEAT_TIF, peat_cells_from_tif

    d = OUT / "peat"
    d.mkdir(exist_ok=True)
    arc = d / "TROP-SUBTROP_PeatV21_2016_CIFOR.7z"
    if not DEFAULT_PEAT_TIF.exists():
        if not arc.exists():
            arc.write_bytes(fetch(PEAT_URL).content)
        with py7zr.SevenZipFile(arc) as z:
            z.extractall(d)
    cells = peat_cells_from_tif(DEFAULT_PEAT_TIF)
    cells.to_parquet(DEFAULT_PEAT_CELLS, index=False)
    print(f"wrote {DEFAULT_PEAT_CELLS.name}: {len(cells):,} cells with peat")
    from burncal.peat import DEFAULT_PEAT_REGIONS, peat_by_region
    peat_by_region(cells).to_parquet(DEFAULT_PEAT_REGIONS, index=False)
    print(f"wrote {DEFAULT_PEAT_REGIONS.name}")


# Sarawak oil palm concessions (SADIA, Aidenvironment & Earthsight via Global Forest Watch, CC BY 4.0)
SARAWAK_OIL_PALM_URL = "https://opendata.arcgis.com/datasets/ff96c17423404ac6951ad77c8cf3f743_7.geojson"


def concessions() -> None:
    d = OUT / "concessions"
    d.mkdir(exist_ok=True)
    out = d / "sarawak_oil_palm.geojson"
    out.write_bytes(fetch(SARAWAK_OIL_PALM_URL).content)
    print(f"wrote {out.name}")


def gfed() -> None:
    sys.path.insert(0, str(ROOT / "src"))
    from burncal.burned_area import DEFAULT_GFED_ZIP, build_gfed_regions

    if not DEFAULT_GFED_ZIP.exists():
        DEFAULT_GFED_ZIP.parent.mkdir(exist_ok=True)
        DEFAULT_GFED_ZIP.write_bytes(fetch(GFED_URL).content)
    out = build_gfed_regions(DEFAULT_GFED_ZIP)
    print(f"wrote {out}")


def main(argv=None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--peat", action="store_true")
    ap.add_argument("--gfed", action="store_true")
    ap.add_argument("--concessions", action="store_true", help="Sarawak oil palm concessions (CC BY 4.0)")
    args = ap.parse_args(argv)
    OUT.mkdir(parents=True, exist_ok=True)

    dmi = fetch(DMI_URL).text
    if "DMI" not in dmi[:200]:
        sys.exit("Unexpected DMI file format")
    (OUT / "dmi.had.long.csv").write_text(dmi, encoding="utf-8")
    print("wrote", OUT / "dmi.had.long.csv")
    asmc_reviews()
    if args.peat:
        peat()
    if args.concessions:
        concessions()
    if args.gfed:
        gfed()

    text = fetch(ONI_URL).text
    if "SEAS" not in text[:200]:
        sys.exit("Unexpected ONI file format")
    (OUT / "oni.ascii.txt").write_text(text, encoding="utf-8")
    print("wrote", OUT / "oni.ascii.txt")

    meta_path = OUT / "geoBoundaries-meta.json"
    meta = json.loads(meta_path.read_text(encoding="utf-8")) if meta_path.exists() else {}
    for iso, level in BOUNDARIES:
        if (OUT / f"geoBoundaries-{iso}-{level}.geojson").exists() and f"{iso}-{level}" in meta:
            continue
        try:
            info = fetch(GB_API.format(release=GB_RELEASE.get((iso, level), "gbOpen"), iso=iso, level=level)).json()
            url = info.get("simplifiedGeometryGeoJSON") or info["gjDownloadURL"]
            gj = fetch(url).json()
        except Exception as e:  # some territories (e.g. HKG) have no geoBoundaries file
            print(f"  {iso}-{level}: not available ({type(e).__name__})")
            continue
        p = OUT / f"geoBoundaries-{iso}-{level}.geojson"
        p.write_text(json.dumps(gj), encoding="utf-8")
        meta[f"{iso}-{level}"] = {k: info.get(k) for k in ("boundaryName", "boundaryYearRepresented",
                                                         "boundaryLicense", "boundarySource", "buildDate")}
        print(f"wrote {p.name}: {len(gj['features'])} features")
    (OUT / "geoBoundaries-meta.json").write_text(json.dumps(meta, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
