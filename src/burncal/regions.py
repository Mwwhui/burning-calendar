"""Assign hotspots to countries, Malaysian states/districts and Indonesian provinces.

Boundaries: geoBoundaries gbOpen simplified GeoJSON in data/external/
(scripts/download_context.py). MYS ADM0/ADM1 are ODbL 1.0 (OpenStreetMap), MYS ADM2 is
CC BY 3.0; attribute them in any published output.

Simplified coastlines cut off some coastal and island fires, so points that fall in no
polygon are snapped to the nearest polygon within `snap_deg` (default 0.05 deg, ~5 km).
Points further out (sea, gas platforms) stay unassigned ("Other").
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

DEFAULT_DIR = Path(__file__).resolve().parents[2] / "data" / "external"
SEA_ISO3 = ("BRN", "KHM", "IDN", "LAO", "MYS", "MMR", "PHL", "SGP", "THA", "TLS", "VNM")
# Asian countries by UN sub-region (Russia on its own: its FIRMS file and boundary cover the whole
# country, European part included). Used for "all of ..." choices; None in the cube/daily helpers
# means all of ASIA_ISO3.
SUBREGIONS: dict[str, tuple[str, ...]] = {
    "Southeast Asia": SEA_ISO3,
    "South Asia": ("AFG", "BGD", "BTN", "IND", "LKA", "MDV", "NPL", "PAK"),
    "East Asia": ("CHN", "HKG", "JPN", "KOR", "MNG", "PRK", "TWN"),
    "Central Asia": ("KAZ", "KGZ", "TJK", "TKM", "UZB"),
    "West Asia": ("ARE", "ARM", "AZE", "BHR", "CYP", "GEO", "IRN", "IRQ", "ISR", "JOR", "KWT", "LBN", "OMN", "PSE",
                  "QAT", "SAU", "SYR", "TUR", "YEM"),
    "Russia": ("RUS",),
}
ASIA_ISO3: tuple[str, ...] = tuple(i for v in SUBREGIONS.values() for i in v)
# Countries studied outside Asia, kept apart so that no Asian total ("None" = all of Asia) includes them.
# Argentina: home of CONAE, the challenge author; shows the method outside Asia.
OTHER_REGIONS: dict[str, tuple[str, ...]] = {"South America": ("ARG",)}
OTHER_ISO3: tuple[str, ...] = tuple(i for v in OTHER_REGIONS.values() for i in v)
STUDY_ISO3: tuple[str, ...] = ASIA_ISO3 + OTHER_ISO3


def as_isos(countries) -> list[str]:
    """None -> all Asian countries (never the OTHER_REGIONS ones); "MYS" -> ["MYS"]; list/tuple -> list."""
    if countries is None:
        return list(ASIA_ISO3)
    return [countries] if isinstance(countries, str) else list(countries)


def _shapely():
    try:
        import shapely
        from shapely import STRtree
    except ImportError as e:  # pragma: no cover
        raise ImportError("Region assignment needs shapely: pip install shapely") from e
    return shapely, STRtree


# Spelling fixes for names in the boundary files (source spelling -> display spelling)
NAME_FIXES = {"Río negro": "Río Negro"}


def load_layer(path: str | Path, name_field: str = "shapeName"):
    """Return (names array, geometries array) from a GeoJSON file."""
    shapely, _ = _shapely()
    gj = json.loads(Path(path).read_text(encoding="utf-8"))
    names = [(f["properties"].get(name_field) or "").strip() or None for f in gj["features"]]
    names = np.array([NAME_FIXES.get(n, n) for n in names], dtype=object)
    geoms = np.array([shapely.from_geojson(json.dumps(f["geometry"])) for f in gj["features"]], dtype=object)
    return names, geoms


def assign(lon, lat, names, geoms, snap_deg: float = 0.05) -> np.ndarray:
    """Name of the polygon containing each point (or nearest within snap_deg), else None."""
    shapely, STRtree = _shapely()
    lon, lat = np.asarray(lon, float), np.asarray(lat, float)
    out = np.full(len(lon), None, dtype=object)
    if len(lon) == 0:
        return out
    pts = shapely.points(lon, lat)
    tree = STRtree(geoms)
    ip, ig = tree.query(pts, predicate="within")
    out[ip] = names[ig]
    missing = np.flatnonzero(pd.isna(out))
    if snap_deg and len(missing):
        mp, mg = tree.query_nearest(pts[missing], max_distance=snap_deg, all_matches=False)
        out[missing[mp]] = names[mg]
    return out


class RegionTagger:
    """Loads every geoBoundaries file in `boundary_dir` once and tags points.

    Country polygons: every geoBoundaries-<ISO3>-ADM0 file (falls back to ADM1 for a
    country without ADM0). Within a country: ADM1 and ADM2 files when present.
    Build it once and call `tag()` per file when processing many files.
    """

    def __init__(self, boundary_dir: str | Path | None = None, snap_deg: float = 0.05):
        d = Path(boundary_dir) if boundary_dir else DEFAULT_DIR
        files = {p.stem.split("-", 1)[1]: p for p in d.glob("geoBoundaries-*-ADM*.geojson")}
        if not files:
            raise FileNotFoundError(f"Boundaries not found in {d}. Run: python scripts/download_context.py")
        self.snap_deg = snap_deg
        isos = sorted({k.split("-")[0] for k in files})
        cn, cg = [], []
        for iso in isos:
            p = files.get(f"{iso}-ADM0") or files.get(f"{iso}-ADM1")
            _, g = load_layer(p)
            cn += [iso] * len(g)
            cg += list(g)
        self.countries = (np.array(cn, dtype=object), np.array(cg, dtype=object))
        self.levels = {}
        for key, p in files.items():
            iso, level = key.split("-")
            if level in ("ADM1", "ADM2"):
                self.levels[(iso, level)] = load_layer(p)

    def tag(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add `country` (ISO3 or "Other"), `adm1` (state/province), `adm2` (district, MYS only so far).

        Only unique coordinates are tested, so repeated detections cost nothing extra.
        """
        coords = df[["longitude", "latitude"]].drop_duplicates().reset_index(drop=True)
        lon, lat = coords["longitude"].to_numpy(), coords["latitude"].to_numpy()
        coords["country"] = assign(lon, lat, *self.countries, self.snap_deg)
        coords["adm1"] = None
        coords["adm2"] = None
        for (iso, level), (names, geoms) in self.levels.items():
            sel = (coords["country"] == iso).to_numpy()
            if sel.any():
                # larger snap inside a country: ADM files are simplified independently
                col = level.lower()
                coords.loc[sel, col] = assign(lon[sel], lat[sel], names, geoms, max(self.snap_deg, 0.1))
        coords["country"] = coords["country"].fillna("Other")
        out = df.drop(columns=[c for c in ("country", "adm1", "adm2") if c in df], errors="ignore")
        return out.merge(coords, on=["longitude", "latitude"], how="left")


def assign_regions(df: pd.DataFrame, boundary_dir: str | Path | None = None, snap_deg: float = 0.05) -> pd.DataFrame:
    """One-off tagging (see RegionTagger to reuse loaded boundaries across files)."""
    return RegionTagger(boundary_dir, snap_deg).tag(df)


def filter_region(df: pd.DataFrame, country: str | None = None, adm1=None, adm2=None) -> pd.DataFrame:
    """Keep rows in the given country and optional state(s)/district(s)."""
    out = df
    if country:
        out = out[out["country"] == country]
    if adm1:
        out = out[out["adm1"].isin([adm1] if isinstance(adm1, str) else list(adm1))]
    if adm2:
        out = out[out["adm2"].isin([adm2] if isinstance(adm2, str) else list(adm2))]
    return out
