"""Data access for the web export (scripts/export_web.py): region options, harmonization runs, daily tables,
events and map borders. Kept apart from the export scripts so it can be tested (tests/test_data_access.py)."""

from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from burncal.calendar import to_grid  # noqa: E402
from burncal.config import Settings  # noqa: E402
from burncal.cube import load_cube  # noqa: E402
from burncal.io import make_demo_data  # noqa: E402
from burncal.pipeline import PipelineResult, run, run_cube  # noqa: E402

CUBE_PATH = ROOT / "data" / "processed" / "cube.parquet"
POINTS_DIR = ROOT / "data" / "processed" / "points"
EXT_DIR = ROOT / "data" / "external"
from burncal.regions import ASIA_ISO3, NAME_FIXES, SUBREGIONS, as_isos  # noqa: E402

COUNTRY_NAMES = {
    "BRN": "Brunei", "KHM": "Cambodia", "IDN": "Indonesia", "LAO": "Laos", "MYS": "Malaysia",
    "MMR": "Myanmar", "PHL": "Philippines", "SGP": "Singapore", "THA": "Thailand",
    "TLS": "Timor-Leste", "VNM": "Vietnam",
    "AFG": "Afghanistan", "BGD": "Bangladesh", "BTN": "Bhutan", "IND": "India", "LKA": "Sri Lanka",
    "MDV": "Maldives", "NPL": "Nepal", "PAK": "Pakistan",
    "CHN": "China", "HKG": "Hong Kong", "JPN": "Japan", "KOR": "South Korea", "MNG": "Mongolia",
    "PRK": "North Korea", "TWN": "Taiwan",
    "KAZ": "Kazakhstan", "KGZ": "Kyrgyzstan", "TJK": "Tajikistan", "TKM": "Turkmenistan", "UZB": "Uzbekistan",
    "ARE": "United Arab Emirates", "ARM": "Armenia", "AZE": "Azerbaijan", "BHR": "Bahrain", "CYP": "Cyprus",
    "GEO": "Georgia", "IRN": "Iran", "IRQ": "Iraq", "ISR": "Israel", "JOR": "Jordan", "KWT": "Kuwait",
    "LBN": "Lebanon", "OMN": "Oman", "PSE": "Palestine", "QAT": "Qatar", "SAU": "Saudi Arabia", "SYR": "Syria",
    "TUR": "Turkey", "YEM": "Yemen",
    "RUS": "Russia (whole country)",
    # outside Asia (burncal.regions.OTHER_REGIONS): never part of an Asian total
    "ARG": "Argentina",
}
ALL_ASIA = "All Asia"
# "country" in this module: an ISO3 code, a tuple of codes (a group) or None (all of Asia)
GROUPS: dict[str, tuple[str, ...] | None] = {ALL_ASIA: None, **{f"All {k}": v for k, v in SUBREGIONS.items()
                                                                 if len(v) > 1}}


def isos(country) -> list[str]:
    return as_isos(country)


def is_single(country) -> bool:
    return isinstance(country, str)


def place_name(country) -> str:
    """Display name of a country or group."""
    if is_single(country):
        return COUNTRY_NAMES.get(country, country)
    for label, members in GROUPS.items():
        if members == (tuple(country) if country is not None else None):
            return label.removeprefix("All ")
    return "selected countries"
POINT_SCHEMA_COLS = {
    "latitude": "float64", "longitude": "float64", "acq_date": "timestamp[ns]", "acq_time": "float64",
    "solar_date": "timestamp[ns]", "satellite": "string", "sensor": "string", "product": "string",
    "confidence": "string", "frp": "float64", "daynight": "string", "type": "float64",
    "country": "string", "adm1": "string", "adm2": "string",
}


def has_cube(path: Path | None = None) -> bool:
    return Path(path or CUBE_PATH).exists()


def get_cube(path: Path | None = None) -> pd.DataFrame:
    return load_cube(path or CUBE_PATH)


def region_options(cube: pd.DataFrame) -> dict:
    """{ISO3: {adm1: [adm2, ...]}} for Asian countries present in the cube, provinces sorted by fire activity."""
    sea = cube[cube["country"].isin(COUNTRY_NAMES)]
    out = {}
    for iso, g in sea.groupby("country"):
        prov = g.dropna(subset=["adm1"]).groupby("adm1")["cell_days"].sum().sort_values(ascending=False)
        out[iso] = {}
        for a1 in prov.index:
            dist = g[(g["adm1"] == a1)].dropna(subset=["adm2"]).groupby("adm2")["cell_days"].sum()
            out[iso][a1] = list(dist.sort_values(ascending=False).index)
    return dict(sorted(out.items(), key=lambda kv: COUNTRY_NAMES[kv[0]]))


def compute(cube: pd.DataFrame | None, country: str | None, adm1: str | None, adm2: str | None) -> PipelineResult:
    """Harmonize the selected region (cube) or the demo data (cube None)."""
    if cube is None:
        return run(make_demo_data(), Settings())
    return run_cube(cube, Settings(country=country, adm1=adm1, adm2=adm2))


def enso_marks() -> dict[int, str]:
    try:
        from burncal.context import enso_by_year, load_oni
        t = enso_by_year(load_oni())
    except FileNotFoundError:
        return {}
    return {int(y): {"El Nino": "El Niño", "La Nina": "La Niña"}[lab] for y, lab in t["label"].items() if lab != "Neutral"}


def partial_month(series: pd.Series, today=None) -> pd.Period | None:
    """The last month with data if it is still running (current calendar month), else None.

    Its count covers only the days so far, so it must not be compared with full months.
    """
    s = series.dropna()
    if s.empty:
        return None
    now = pd.Period(pd.Timestamp(today) if today is not None else pd.Timestamp.today(), "M")
    last = s.index.max()
    return last if last >= now else None


def calendar_frames(res: PipelineResult, today=None) -> dict[str, pd.DataFrame]:
    f = res.harmonization.frame
    part = partial_month(f["harmonized"], today)
    is_partial = pd.Series(f.index == part if part is not None else False, index=f.index)
    return {
        "value": to_grid(f["harmonized"]),
        "lower": to_grid(f["lower"]),
        "upper": to_grid(f["upper"]),
        "estimated": to_grid(~f["source"].str.endswith("measured")).astype(bool),
        "partial": to_grid(is_partial).fillna(False).astype(bool),
        "source": to_grid(f["source"]),
    }


def cumulative_by_year(series: pd.Series) -> pd.DataFrame:
    """Rows = month 1..12, columns = year, values = cumulative total (NaN after the last month with data)."""
    g = to_grid(series)
    return g.cumsum(axis=1).where(g.notna()).T


def summary_numbers(res: PipelineResult, today=None) -> dict:
    """Headline numbers. A still-running current month is left out of the season-to-date
    comparison (it holds only the days so far)."""
    s = res.harmonization.series.dropna()
    part = partial_month(s, today)
    if part is not None:
        s = s[s.index < part]
    grid = to_grid(s)
    annual = grid.sum(axis=1, min_count=12)
    src = res.harmonization.frame["source"]
    clim = grid.mean()
    last = s.index.max()
    from burncal.calendar import season_to_date
    std = season_to_date(s, last.year)
    return {
        "peak_month": int(clim.idxmax()),
        "peak_share": float(clim.max() / clim.sum()) if clim.sum() > 0 else np.nan,
        "busiest_year": int(annual.idxmax()) if annual.notna().any() else None,
        "busiest_year_total": float(annual.max()) if annual.notna().any() else np.nan,
        "busiest_year_estimated": bool(annual.notna().any() and not src[src.index.year == int(annual.idxmax())]
                                       .str.endswith("measured").all()),
        "partial_month": str(part) if part is not None else None,
        "busiest_ties": busiest_ties(res),
        "this_year": int(last.year),
        "through_month": int(std.attrs["through_month"]),
        "this_year_to_date": float(std.loc[last.year, "to_date"]),
        "rank": int(std.loc[last.year, "rank"]),
        "n_years": int(std["to_date"].notna().sum()),
        "pct_vs_median": float(std.attrs["pct_vs_median"]),
    }


def too_few_fires(res: PipelineResult) -> str | None:
    """First month shown, when older satellites could not be converted because the area has
    too few fires (Settings.min_fire_pairs); None when every conversion step that had
    something to fill was applied."""
    if not any(s.reason.startswith("too few fires") or ": too few fires" in s.reason
               for s in res.harmonization.steps):
        return None
    s = res.harmonization.series.dropna()
    return str(s.index.min()) if not s.empty else "none"


def busiest_ties(res: PipelineResult) -> list[int]:
    """Other complete years whose 90 % annual range overlaps the busiest year's range,
    i.e. years that cannot be ruled out as the busiest."""
    a = res.harmonization.annual()
    if a.empty:
        return []
    top = int(a["total"].idxmax())
    ties = a[(a.index != top) & (a["upper"] >= a.loc[top, "lower"])]
    return [int(y) for y in ties.sort_values("total", ascending=False).index]  # closest first


def read_points(country, adm1, adm2, start, end, limit: int = 500_000,
                points_dir: Path = POINTS_DIR, satellites=None) -> tuple[pd.DataFrame, bool]:
    """Cleaned hotspots for a region and date range from the per-file Parquet points.

    Returns (rows, truncated). Columns that are entirely empty in some files are read
    with a fixed schema so files can be combined.
    """
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.dataset as ds

    schema = pa.schema([(c, pa.type_for_alias(t) if t != "timestamp[ns]" else pa.timestamp("ns"))
                        for c, t in POINT_SCHEMA_COLS.items()])
    dset = ds.dataset(str(points_dir), format="parquet", schema=schema)
    flt = (pc.field("solar_date") >= pa.scalar(pd.Timestamp(start), pa.timestamp("ns"))) & \
          (pc.field("solar_date") <= pa.scalar(pd.Timestamp(end), pa.timestamp("ns")))
    flt &= pc.field("country").isin(isos(country))
    if adm1:
        flt &= pc.field("adm1") == adm1
    if adm2:
        flt &= pc.field("adm2") == adm2
    if satellites:
        flt &= pc.field("satellite").isin(list(satellites))
    tbl = ds.Scanner.from_dataset(dset, filter=flt).head(limit + 1)
    df = tbl.to_pandas()
    truncated = len(df) > limit
    return df.head(limit), truncated


# ----------------------------------------------------------------------------- map helpers
SAT_LABEL = {"NOAA20": "NOAA-20 VIIRS (375 m)", "SNPP": "Suomi NPP VIIRS (375 m)",
             "Aqua": "Aqua MODIS (1 km)", "Terra": "Terra MODIS (1 km)"}


def satellite_for_month(month) -> str:
    """The most detailed satellite flying in a month, used alone for the fire-dot map
    (several satellites would show the same fire several times)."""
    m = pd.Period(month, "M")
    if m >= pd.Period("2018-04", "M"):
        return "NOAA20"
    if m >= pd.Period("2012-01", "M"):
        return "SNPP"
    return "Aqua" if m >= pd.Period("2002-07", "M") else "Terra"


def _km2(geom) -> float:
    """Approximate area of a lon/lat polygon in km2."""
    c = geom.centroid
    return float(geom.area * 111.32 ** 2 * np.cos(np.radians(c.y)))


def load_areas(level: str, country: str | None = None, adm1: str | None = None,
               ext_dir: Path = EXT_DIR) -> dict | None:
    """Simplified boundaries for the map.

    level "country": the countries of `country` (None = all of Asia; ids = ISO3); "adm1": states/provinces of `country`;
    "adm2": Malaysian districts inside state `adm1`. Returns {"geojson", "ids", "names",
    "km2", "bounds" (per id), "extent"} or None if the boundary files are missing.
    Names match the cube (both come from geoBoundaries shapeName).
    """
    import json

    import shapely

    def read(path, tol):
        if not path.exists():
            return []
        gj = json.loads(path.read_text(encoding="utf-8"))
        out = []
        for f in gj["features"]:
            name = (f["properties"].get("shapeName") or "").strip()
            name = NAME_FIXES.get(name, name)  # same spelling as the cube (burncal.regions.load_layer)
            g = shapely.from_geojson(json.dumps(f["geometry"]))
            out.append((name, g, shapely.simplify(g, tol, preserve_topology=True)))
        return out

    feats = []  # (id, display name, full geometry, simplified geometry)
    if level == "country":
        for iso in isos(country):
            parts = read(ext_dir / f"geoBoundaries-{iso}-ADM0.geojson", 0.02)
            if parts:
                full = shapely.union_all([p[1] for p in parts])
                feats.append((iso, COUNTRY_NAMES[iso], full, shapely.union_all([p[2] for p in parts])))
    elif level == "adm1":
        for name, g, simp in read(ext_dir / f"geoBoundaries-{country}-ADM1.geojson", 0.01):
            feats.append((name, name, g, simp))
    elif level == "adm2":
        states = {n: g for n, g, _ in read(ext_dir / f"geoBoundaries-{country}-ADM1.geojson", 0.01)}
        if adm1 not in states:
            return None
        state = shapely.buffer(states[adm1], 0.01)
        for name, g, simp in read(ext_dir / f"geoBoundaries-{country}-ADM2.geojson", 0.003):
            if state.contains(g.representative_point()):  # district names can repeat across states
                feats.append((name, name, g, simp))
    if not feats:
        return None
    features = []
    for fid, _, _, simp in feats:
        simp = shapely.set_precision(simp, 0.001)
        features.append({"type": "Feature", "id": fid, "properties": {},
                         "geometry": json.loads(shapely.to_geojson(simp))})
    bounds = {fid: tuple(float(v) for v in g.bounds) for fid, _, g, _ in feats}
    b = np.array(list(bounds.values()))
    return {"geojson": {"type": "FeatureCollection", "features": features},
            "ids": [f[0] for f in feats], "names": {f[0]: f[1] for f in feats},
            "km2": {fid: _km2(g) for fid, _, g, _ in feats}, "bounds": bounds,
            "extent": (float(b[:, 0].min()), float(b[:, 1].min()), float(b[:, 2].max()), float(b[:, 3].max()))}


def map_level(country: str | None, adm1: str | None) -> tuple[str, str | None, str | None]:
    """Which areas the map shows for the current selection: (level, country, adm1)."""
    if not is_single(country):
        return "country", country, None
    if adm1 and country == "MYS":
        return "adm2", country, adm1
    return "adm1", country, None


def area_change(cube: pd.DataFrame, level: str, country: str | None = None, adm1: str | None = None,
                year: int | None = None, today=None, first_base_year: int = 2019,
                min_base: float = 10.0) -> pd.DataFrame:
    """Fire activity per area in `year` (default: latest) vs the average of the other full
    years since `first_base_year`, over the same months (Jan..last complete month).

    Uses measured NOAA-20 only, so no conversion is involved. Columns: this, typical,
    change_pct (NaN where the typical value is below `min_base` fire days: too few fires to
    compare). attrs: year, through_month, base_years.
    """
    col = {"country": "country", "adm1": "adm1", "adm2": "adm2"}[level]
    noaa = cube[cube["satellite"] == "NOAA20"]
    months = pd.PeriodIndex(noaa["month"].unique(), freq="M").sort_values()
    now = pd.Period(pd.Timestamp(today) if today is not None else pd.Timestamp.today(), "M")
    last = months[months < now].max()
    if year is None or year >= last.year:
        year, through = int(last.year), int(last.month)
    else:
        year, through = int(year), 12
    first_full = int(months.min().year) + (0 if months.min().month == 1 else 1)
    last_full = int(last.year) if last.month == 12 else int(last.year) - 1
    base_years = [y for y in range(max(first_base_year, first_full), last_full + 1) if y != year]
    sub = noaa[noaa["country"].isin(isos(country))] if level == "country" else noaa[noaa["country"] == country]
    if level == "adm2":
        sub = sub[sub["adm1"] == adm1]
    per = pd.PeriodIndex(sub["month"], freq="M")
    sub = sub[np.asarray(per.month <= through)]
    yrs = pd.PeriodIndex(sub["month"], freq="M").year
    by = sub.groupby([sub[col].to_numpy(), yrs])["cell_days"].sum().unstack(fill_value=0.0)
    this = by[year] if year in by.columns else pd.Series(0.0, index=by.index)
    base = by.reindex(columns=base_years, fill_value=0.0).mean(axis=1) if base_years \
        else pd.Series(np.nan, index=by.index)
    out = pd.DataFrame({"this": this.astype(float), "typical": base.astype(float)})
    out["change_pct"] = (100 * (out["this"] / out["typical"] - 1)).where(out["typical"] >= min_base)
    out.index.name = "id"
    out.attrs.update({"year": year, "through_month": through, "base_years": base_years})
    return out


def rough_years_note(res: PipelineResult, threshold_pct: float = 50.0) -> float | None:
    """Typical half-width (%) of the yearly likely range for 2003-2011 when it is wider than
    `threshold_pct`, i.e. when old years are too rough to compare one by one; else None."""
    a = res.harmonization.annual()
    old = a.loc[2003:2011]
    old = old[old["estimated_share"] > 0]
    if old.empty:
        return None
    hw = float((100 * (old["upper"] - old["lower"]) / 2 / old["total"]).median())
    return hw if np.isfinite(hw) and hw > threshold_pct else None


def map_zoom(extent: tuple[float, float, float, float], width_px: int = 560) -> tuple[dict, float]:
    """Centre and zoom so the extent (lon0, lat0, lon1, lat1) fits a map about `width_px` wide.

    Plotly's maps use 512 px tiles: at zoom z a map W px wide shows W * 360 / (512 * 2**z) degrees.
    15 % margin around the extent."""
    lon0, lat0, lon1, lat1 = extent
    span = max(lon1 - lon0, (lat1 - lat0) * 1.6, 0.05) * 1.15
    zoom = float(np.clip(np.log2(width_px * 360 / (512 * span)), 1, 11))
    return {"lon": (lon0 + lon1) / 2, "lat": (lat0 + lat1) / 2}, zoom


def month_options(res: PipelineResult) -> list[pd.Period]:
    """Months with data, oldest first (for the fire-dot map)."""
    s = res.harmonization.series.dropna()
    return list(s.index)


# ----------------------------------------------------------------------------- daily data, own areas
DAILY_ADMIN = ROOT / "data" / "processed" / "daily_admin.parquet"
DAILY_GRID = ROOT / "data" / "processed" / "daily_grid.parquet"


def has_daily(admin_path: Path | None = None, grid_path: Path | None = None) -> bool:
    return Path(admin_path or DAILY_ADMIN).exists() and Path(grid_path or DAILY_GRID).exists()


def get_daily(admin_path: Path | None = None, grid_path: Path | None = None):
    from burncal.daily import load_daily
    return load_daily(admin_path or DAILY_ADMIN), load_daily(grid_path or DAILY_GRID)


def compute_custom(cube: pd.DataFrame, grid: pd.DataFrame, keys) -> PipelineResult:
    """Harmonize a user-defined area (a set of 0.1 deg area cells) exactly like a listed region."""
    from burncal.cube import platform_coverage
    from burncal.daily import daily_for_cells, monthly_from_daily
    from burncal.pipeline import run_monthly

    monthly = monthly_from_daily(daily_for_cells(grid, keys), platform_coverage(cube))
    return run_monthly(monthly, Settings())


def draw_grid(country, ext_dir: Path | None = None, area_deg: float | None = None,
              max_points: int = 60_000) -> pd.DataFrame:
    """Centres of drawing squares on land in a country or group (None = all Asia).

    Squares are the 0.1 deg area cells when there are at most `max_points` of them; for big
    countries a coarser square (0.2, 0.5 or 1 deg) is shown so the map stays fast, and a drawn
    coarse square is turned back into its 0.1 deg cells by `expand_drawn`.
    Columns: key (0.1 deg key, or -1 for coarse squares), lat, lon, deg."""
    import json

    import shapely

    from burncal.daily import AREA_DEG, box_cells, key_to_cell

    ext_dir = Path(ext_dir or EXT_DIR)
    geoms = []
    for iso in isos(country):
        p = ext_dir / f"geoBoundaries-{iso}-ADM0.geojson"
        if p.exists():
            gj = json.loads(p.read_text(encoding="utf-8"))
            geoms += [shapely.from_geojson(json.dumps(f["geometry"])) for f in gj["features"]]
    if not geoms:
        return pd.DataFrame(columns=["key", "lat", "lon", "deg"])
    base = area_deg or AREA_DEG
    land0 = shapely.simplify(shapely.union_all(geoms), 0.02)
    for deg in (base, 0.2, 0.5, 1.0):
        if deg < base:
            continue
        land = shapely.buffer(land0, deg * 0.7)
        w, s, e, n = land.bounds
        keys = box_cells(w, s, e, n, deg)
        gy, gx = key_to_cell(keys)
        lat, lon = (gy + 0.5) * deg, (gx + 0.5) * deg
        ok = shapely.contains_xy(land, lon, lat)
        if ok.sum() <= max_points or deg == 1.0:
            break
    return pd.DataFrame({"key": keys[ok] if deg == base else -1, "lat": lat[ok], "lon": lon[ok], "deg": deg})


def expand_drawn(lat, lon, deg: float) -> list[int]:
    """0.1 deg area-cell keys inside a drawn square of size `deg` centred at lat/lon."""
    from burncal.daily import box_cells
    h = deg / 2
    return [int(k) for k in box_cells(lon - h, lat - h, lon + h, lat + h)]


def read_points_cells(keys, start, end, limit: int = 600_000, satellites=None,
                      points_dir: Path = POINTS_DIR) -> tuple[pd.DataFrame, bool]:
    """Cleaned hotspots inside a user-defined area (set of area cells) between two dates."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.dataset as ds

    from burncal.daily import AREA_DEG, cell_key, cells_extent

    w, s, e, n = cells_extent(keys)
    schema = pa.schema([(c, pa.type_for_alias(t) if t != "timestamp[ns]" else pa.timestamp("ns"))
                        for c, t in POINT_SCHEMA_COLS.items()])
    dset = ds.dataset(str(points_dir), format="parquet", schema=schema)
    flt = (pc.field("solar_date") >= pa.scalar(pd.Timestamp(start), pa.timestamp("ns"))) & \
          (pc.field("solar_date") <= pa.scalar(pd.Timestamp(end), pa.timestamp("ns"))) & \
          (pc.field("latitude") >= s) & (pc.field("latitude") <= n) & \
          (pc.field("longitude") >= w) & (pc.field("longitude") <= e)
    if satellites:
        flt &= pc.field("satellite").isin(list(satellites))
    df = ds.Scanner.from_dataset(dset, filter=flt).to_table().to_pandas()
    # same cell rule as burncal.daily: the ~1 km cell centre decides the area cell
    lat_c = (np.floor(df["latitude"] / 0.01) + 0.5) * 0.01
    lon_c = (np.floor(df["longitude"] / 0.01) + 0.5) * 0.01
    k = cell_key(np.floor(lat_c / AREA_DEG), np.floor(lon_c / AREA_DEG))
    df = df[np.isin(k, np.asarray(keys, "int64"))]
    truncated = len(df) > limit
    return df.head(limit).reset_index(drop=True), truncated


def window_summary(res: PipelineResult, daily: pd.DataFrame, start, end, last_day):
    """(per-year totals for the same dates, comparison of the end year vs the median)."""
    from burncal.daily import compare_window, window_totals

    tot = window_totals(res.harmonization.frame, daily, start, end, last_day)
    return tot, compare_window(tot, pd.Timestamp(end).year)


def satellite_for_window(start, end) -> str:
    """The most detailed satellite that flew over the whole window (for the fire-dot map).
    One satellite only, so the same fire is not drawn several times."""
    s, e = pd.Timestamp(start), pd.Timestamp(end)
    if s >= pd.Timestamp("2018-04-01"):
        return "NOAA20"
    if s >= pd.Timestamp("2012-01-20") and e <= pd.Timestamp("2026-11-02"):
        return "SNPP"
    if s >= pd.Timestamp("2002-07-04") and e <= pd.Timestamp("2026-08-26"):
        return "Aqua"
    return "Terra"


# ----------------------------------------------------------------------------- peat split
def has_peat(admin: pd.DataFrame) -> bool:
    return "peat" in admin and bool(admin["peat"].any())


def compute_peat(cube: pd.DataFrame, admin: pd.DataFrame, grid: pd.DataFrame, country, adm1, adm2, keys,
                 peat: bool) -> PipelineResult:
    """Harmonize only the fires on (peat=True) or off (False) mapped peat, with the same chain."""
    from burncal.cube import platform_coverage
    from burncal.daily import daily_for_cells, daily_for_region, monthly_from_daily
    from burncal.pipeline import run_monthly

    d = daily_for_cells(grid, keys, peat=peat) if keys else daily_for_region(admin, country, adm1, adm2, peat=peat)
    return run_monthly(monthly_from_daily(d, platform_coverage(cube)), Settings())


def peat_km2(country, adm1, keys, ext_dir: Path | None = None) -> float | None:
    """Mapped peat area (km2) inside a listed region or own area; None without the peat tables."""
    ext = Path(ext_dir or EXT_DIR)
    if keys:
        p = ext / "peat_cells.parquet"
        if not p.exists():
            return None
        from burncal.daily import AREA_DEG, cell_key
        c = pd.read_parquet(p)
        lat = (c["cell_y"] + 0.5) * 0.01
        km2 = c["peat_share"] * (111.32 * 0.01) ** 2 * np.cos(np.radians(lat))
        k = cell_key(np.floor(lat / AREA_DEG), np.floor((c["cell_x"] + 0.5) * 0.01 / AREA_DEG))
        return float(km2[np.isin(k, np.asarray(keys, "int64"))].sum())
    p = ext / "peat_regions.parquet"
    if not p.exists():
        return None
    t = pd.read_parquet(p)
    sel = t["country"].isin(isos(country))
    if adm1:
        sel &= t["adm1"] == adm1
    return float(t.loc[sel, "km2"].sum())


# ----------------------------------------------------------------------------- fire events
EVENTS = ROOT / "data" / "processed" / "events.parquet"


def has_events(path: Path | None = None) -> bool:
    return Path(path or EVENTS).exists()


def get_events(path: Path | None = None, columns: list[str] | None = None, compact: bool = False) -> pd.DataFrame:
    from burncal.events import load_events
    return load_events(path or EVENTS, columns=columns, compact=compact)


def events_in(ev: pd.DataFrame, country=None, adm1=None, adm2=None, keys=()) -> pd.DataFrame:
    """Events of a listed region (by the region of most detections) or own area (by the event centre)."""
    if keys:
        from burncal.daily import AREA_DEG, cell_key
        k = cell_key(np.floor(ev["lat"] / AREA_DEG), np.floor(ev["lon"] / AREA_DEG))
        return ev[np.isin(k, np.asarray(keys, "int64"))]
    sel = ev["country"].isin(isos(country))
    if adm1:
        sel &= ev["adm1"] == adm1
    if adm2:
        sel &= ev["adm2"] == adm2
    return ev[sel]


def event_points(e: pd.Series, points_dir: Path = POINTS_DIR) -> pd.DataFrame:
    """NOAA-20 detections inside an event's box and dates (for drawing it)."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.dataset as ds

    schema = pa.schema([(c, pa.type_for_alias(t) if t != "timestamp[ns]" else pa.timestamp("ns"))
                        for c, t in POINT_SCHEMA_COLS.items()])
    dset = ds.dataset(str(points_dir), format="parquet", schema=schema)
    flt = ((pc.field("satellite") == "NOAA20")
           & (pc.field("solar_date") >= pa.scalar(pd.Timestamp(e["start"]), pa.timestamp("ns")))
           & (pc.field("solar_date") <= pa.scalar(pd.Timestamp(e["end"]), pa.timestamp("ns")))
           & (pc.field("latitude") >= e["south"]) & (pc.field("latitude") <= e["north"])
           & (pc.field("longitude") >= e["west"]) & (pc.field("longitude") <= e["east"]))
    cols = ["latitude", "longitude", "solar_date", "frp", "daynight"]
    return ds.Scanner.from_dataset(dset, filter=flt, columns=cols).to_table().to_pandas()


# ----------------------------------------------------------------------------- outlook
def season_outlook(res: PipelineResult, today=None) -> dict | None:
    from burncal.context import load_oni
    from burncal.outlook import outlook

    try:
        oni = load_oni()
    except FileNotFoundError:
        return None
    s = res.harmonization.series.dropna()
    last = partial_month(s, today)
    if last is not None:  # an unfinished month would look like a quiet one
        s = s[s.index < last]
    return outlook(s, oni, pd.Timestamp(today) if today is not None else None)


# ----------------------------------------------------------------------------- checks
GFED_REGIONS = EXT_DIR / "gfed5_regions.parquet"


def official_check(res: PipelineResult, country) -> dict | None:
    """Indonesia only: harmonized yearly totals vs SiPongi burned area."""
    if country != "IDN":
        return None
    from burncal.official import compare_with_official
    a = res.harmonization.annual()
    return compare_with_official(a["total"]) if not a.empty else None


def burned_area_check(res: PipelineResult, country, adm1, path: Path | None = None) -> dict | None:
    path = Path(path or GFED_REGIONS)
    if not path.exists():
        return None
    from burncal.burned_area import compare_burned_area, gfed_monthly, load_gfed_regions
    g = gfed_monthly(load_gfed_regions(path), country, adm1)
    if g["total"].sum() <= 0:
        return None
    from burncal.burned_area import seam_steps
    from burncal.pipeline import naive_series
    out = compare_burned_area(res.harmonization.series, g)
    out["gfed"] = g
    out["steps"] = seam_steps(res.harmonization.series, g)
    out["steps_naive"] = seam_steps(naive_series(res.monthly), g)
    return out


DETAIL = ROOT / "data" / "processed" / "detail_admin.parquet"


def satellite_differences(country, adm1, years=(2019, 2020), path: Path | None = None) -> dict | None:
    """Why satellites disagree: per satellite, detections, day/night share and weak-fire share
    in years when all four flew (same fires, same area)."""
    path = Path(path or DETAIL)
    if not path.exists():
        return None
    t = pd.read_parquet(path)
    t = t[t["year"].isin(years) & t["country"].isin(isos(country))]
    if adm1:
        t = t[t["adm1"] == adm1]
    if t.empty:
        return None
    by = t.groupby("satellite")["detections"].sum()
    night = t[t["daynight"] == "N"].groupby("satellite")["detections"].sum().reindex(by.index).fillna(0) / by
    weak = t[t["frp_class"].isin(["<5 MW", "5-10 MW"])].groupby("satellite")["detections"].sum().reindex(
        by.index).fillna(0) / by
    frp = t.pivot_table(index="satellite", columns="frp_class", values="detections", aggfunc="sum").fillna(0)
    order = [s for s in ("Terra", "Aqua", "SNPP", "NOAA20", "NOAA21") if s in by.index]
    ref = by.get("NOAA20", np.nan)
    tab = pd.DataFrame({"detections": by, "vs_noaa20": by / ref, "night_share": night, "weak_share": weak}).loc[order]
    return {"years": years, "table": tab, "frp": frp.loc[order].div(frp.loc[order].sum(axis=1), axis=0)}


# ----------------------------------------------------------------------------- totals by area (like CONAE "Totalizar")
def totals_by_area(cube: pd.DataFrame, country: str | None, adm1: str | None, start=None, end=None) -> pd.DataFrame:
    """Raw monthly fire days per satellite for each sub-area of the selection (countries of SEA,
    states of a country, or districts of a Malaysian state). Not converted: one column per satellite,
    so periods are comparable only within one satellite."""
    level, c, a1 = map_level(country, adm1)
    col = {"country": "country", "adm1": "adm1", "adm2": "adm2"}[level]
    sub = cube[cube["country"].isin(isos(c))] if level == "country" else cube[cube["country"] == c]
    if level == "adm2":
        sub = sub[sub["adm1"] == a1]
    if start is not None:
        sub = sub[sub["month"] >= pd.Period(pd.Timestamp(start), "M")]
    if end is not None:
        sub = sub[sub["month"] <= pd.Period(pd.Timestamp(end), "M")]
    t = sub.groupby([col, "month", "satellite"])["cell_days"].sum().unstack("satellite", fill_value=0).reset_index()
    t = t.rename(columns={col: {"country": "country", "adm1": "state_province", "adm2": "district"}[level]})
    t["month"] = t["month"].astype(str)
    return t


def area_layer_geojson(areas: dict, change: pd.DataFrame) -> dict:
    """Map layer for GIS (QGIS etc.): area outlines with this year's fire days, normal and change."""
    import copy
    gj = copy.deepcopy(areas["geojson"])
    for f in gj["features"]:
        fid = f["id"]
        r = change.loc[fid] if fid in change.index else None
        f["properties"] = {
            "name": areas["names"][fid], "km2": round(areas["km2"][fid], 1),
            "fire_days": None if r is None else float(r["this"]),
            "normal": None if r is None or pd.isna(r["typical"]) else round(float(r["typical"]), 1),
            "change_pct": None if r is None or pd.isna(r["change_pct"]) else round(float(r["change_pct"]), 1),
            "year": change.attrs.get("year"), "through_month": change.attrs.get("through_month"),
        }
    return gj
