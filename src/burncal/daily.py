"""Daily counts for any area and date range.

The monthly cube answers "which months/years burn most". Two questions in the challenge
need days: "compare the burning activity of the current month against the historical
median" (the current month is only partly over, so the same days must be compared) and
"select a region and a specific date range". Users may also draw their own area.

Two tables are built once from the cleaned points (scripts/build_daily.py):

- daily_admin.parquet: cell-days per local solar date x satellite x country/adm1/adm2,
  counted exactly like the cube (each ~1 km cell once per day per satellite, per file),
  so a month of daily_admin sums to the cube.
- daily_grid.parquet: the same cell-days per date x satellite x 0.1 deg area cell
  (~11 km). A user's own area (drawn, circle or box) is a set of these area cells.

Both tables carry a `peat` flag (the ~1 km cell is at least half mapped peat, see
burncal.peat) when the peat cells are available, so any area can be split into fires on
peat and fires elsewhere. Summing over the flag gives the plain totals.

Harmonization stays monthly (the conversions were fitted and tested on months). A date
window is answered by splitting each converted month by the share of that month's raw
detections, from the same satellite(s) the month was converted from, that fall inside
the window. Within one satellite a share is a like-for-like ratio, so no new conversion
is introduced.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

from .aggregate import add_cells

AREA_DEG = 0.1  # area cell size for user-defined areas
REGION_COLS = ["country", "adm1", "adm2"]
KEY_MULT = 100_000  # area cell key = gy * KEY_MULT + gx (|gx| < KEY_MULT / 2)


# ----------------------------------------------------------------------------- building
def daily_tables(points: pd.DataFrame, grid_deg: float = 0.01, area_deg: float = AREA_DEG,
                 peat_cells: pd.DataFrame | None = None):
    """(admin, grid) daily cell-days for one file's cleaned, tagged points."""
    if points.empty:
        return (pd.DataFrame(columns=["date", "satellite", *REGION_COLS, "peat", "cell_days"]),
                pd.DataFrame(columns=["date", "satellite", "gy", "gx", *REGION_COLS, "peat", "cell_days"]))
    d = points[["latitude", "longitude", "solar_date", "satellite", *REGION_COLS]].copy()
    for c in REGION_COLS:
        d[c] = d[c].astype(object).where(d[c].notna(), "")
    d = add_cells(d, grid_deg).drop_duplicates(["satellite", "cell_y", "cell_x", "solar_date"])
    d = d.rename(columns={"solar_date": "date"})
    # area cell from the ~1 km cell centre, so a 1 km cell never splits between area cells
    lat_c = (d["cell_y"] + 0.5) * grid_deg
    lon_c = (d["cell_x"] + 0.5) * grid_deg
    if peat_cells is not None:
        from .peat import on_peat
        d["peat"] = on_peat(lat_c, lon_c, peat_cells, grid_deg)
    else:
        d["peat"] = False
    admin = d.groupby(["date", "satellite", *REGION_COLS, "peat"]).size().rename("cell_days").reset_index()
    d["gy"] = np.floor(lat_c / area_deg).astype("int32")
    d["gx"] = np.floor(lon_c / area_deg).astype("int32")
    # region columns too, so a listed region can be drawn cell by cell (playback map)
    grid = d.groupby(["date", "satellite", "gy", "gx", *REGION_COLS, "peat"]).size().rename("cell_days").reset_index()
    return admin, grid


def build_daily(points_dir: str | Path, out_dir: str | Path, progress: bool = True,
                peat_cells: pd.DataFrame | None = None, cache_dir: str | Path | None = None) -> tuple[Path, Path]:
    """Build daily_admin.parquet and daily_grid.parquet from every points file.

    With `cache_dir`, each points file's daily tables are kept there and reused while the
    file is unchanged (same size and modification time, same peat setting), so a daily update
    only recomputes the files that changed (the newest NRT downloads). The result is the
    same as without the cache."""
    import json as _json

    points_dir, out_dir = Path(points_dir), Path(out_dir)
    files = sorted(points_dir.glob("*.parquet"))
    admins, grids = [], []
    cols = ["latitude", "longitude", "solar_date", "satellite", *REGION_COLS]
    cache = Path(cache_dir) if cache_dir else None
    if cache:
        cache.mkdir(parents=True, exist_ok=True)
        for old in cache.glob("*.json"):  # parts of points files that no longer exist
            if not (points_dir / f"{old.stem}.parquet").exists():
                for x in cache.glob(f"{old.stem}.*"):
                    x.unlink()
    reused = 0
    for i, f in enumerate(files, 1):
        key = f"{f.stat().st_size}-{f.stat().st_mtime_ns}-peat{peat_cells is not None}"
        meta = cache / f"{f.stem}.json" if cache else None
        if meta is not None and meta.exists() and _json.loads(meta.read_text()).get("key") == key:
            a = pd.read_parquet(cache / f"{f.stem}.admin.parquet")
            g = pd.read_parquet(cache / f"{f.stem}.grid.parquet")
            reused += 1
        else:
            p = pd.read_parquet(f, columns=cols)
            a, g = daily_tables(p, peat_cells=peat_cells)
            if meta is not None:
                a.to_parquet(cache / f"{f.stem}.admin.parquet", index=False)
                g.to_parquet(cache / f"{f.stem}.grid.parquet", index=False)
                meta.write_text(_json.dumps({"key": key}))
        if not cache:
            admins.append(a)
            grids.append(g)
        if progress:
            print(f"\r{i}/{len(files)} points files", end="", flush=True)
    if progress:
        print(f"  ({reused} of {len(files)} files reused from the cache)" if cache else "")
    pa_, pg_ = out_dir / "daily_admin.parquet", out_dir / "daily_grid.parquet"
    if cache:
        stems = [f.stem for f in files]
        _combine_by_year([cache / f"{x}.admin.parquet" for x in stems], ["date", "satellite", *REGION_COLS, "peat"], pa_)
        _combine_by_year([cache / f"{x}.grid.parquet" for x in stems],
                         ["date", "satellite", "gy", "gx", *REGION_COLS, "peat"], pg_)
        return pa_, pg_
    admin = pd.concat(admins, ignore_index=True).groupby(["date", "satellite", *REGION_COLS, "peat"],
                                                          as_index=False)["cell_days"].sum()
    grid = pd.concat(grids, ignore_index=True).groupby(["date", "satellite", "gy", "gx", *REGION_COLS, "peat"],
                                                        as_index=False)["cell_days"].sum()
    for t in (admin, grid):
        t["date"] = pd.to_datetime(t["date"]).dt.normalize()
        t["satellite"] = t["satellite"].astype("category")
        t["cell_days"] = t["cell_days"].astype("int32")
    for c in REGION_COLS:
        admin[c] = admin[c].astype("category")
        grid[c] = grid[c].astype("category")
    grid[["gy", "gx"]] = grid[["gy", "gx"]].astype("int16")
    pa, pg = out_dir / "daily_admin.parquet", out_dir / "daily_grid.parquet"
    admin.to_parquet(pa, index=False)
    grid.to_parquet(pg, index=False)
    return pa, pg


def _combine_by_year(paths: list[Path], keys: list[str], out: Path) -> None:
    """Sum cell-days over `keys` across per-file parts, one calendar year at a time, appending
    to one Parquet file. Memory holds one year, not the whole table (all of Asia: ~31 M grid
    rows, which did not fit when combined at once). Same result as concat + groupby."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.dataset as ds
    import pyarrow.parquet as pq

    fields = {"date": pa.timestamp("ns"), "satellite": pa.string(), "gy": pa.int32(), "gx": pa.int32(),
              "country": pa.string(), "adm1": pa.string(), "adm2": pa.string(), "peat": pa.bool_(),
              "cell_days": pa.int64()}
    cols = [*keys, "cell_days"]
    dset = ds.dataset([str(p) for p in paths], format="parquet", schema=pa.schema([(c, fields[c]) for c in cols]))
    dates = dset.to_table(columns=["date"]).column("date")
    if len(dates) == 0:
        raise ValueError("no daily rows to combine")
    y0 = pc.min(dates).as_py().year
    y1 = pc.max(dates).as_py().year
    # same types as the in-memory build writes (dates in microseconds, small integers)
    out_type = {"gy": pa.int16(), "gx": pa.int16(), "cell_days": pa.int32(), "date": pa.timestamp("us")}
    out_fields = [(c, out_type.get(c, fields[c])) for c in cols]
    out_schema = pa.schema(out_fields)
    tmp = out.with_suffix(".parquet.part")
    writer = pq.ParquetWriter(tmp, out_schema, compression="snappy")
    try:
        for y in range(y0, y1 + 1):
            lo = pa.scalar(pd.Timestamp(y, 1, 1), pa.timestamp("ns"))
            hi = pa.scalar(pd.Timestamp(y + 1, 1, 1), pa.timestamp("ns"))
            t = dset.to_table(filter=(pc.field("date") >= lo) & (pc.field("date") < hi))
            if t.num_rows == 0:
                continue
            # group in Arrow (no pandas string columns): cheap in memory
            g = t.group_by(keys, use_threads=True).aggregate([("cell_days", "sum")])
            g = g.rename_columns([*keys, "cell_days"] if g.column_names[-1] != "cell_days" else g.column_names)
            g = g.select(cols)
            writer.write_table(g.cast(out_schema))
    finally:
        writer.close()
    tmp.replace(out)


FRP_BINS = [0, 5, 10, 50, np.inf]  # MW; MODIS rarely detects fires below ~10 MW, VIIRS sees many
FRP_LABELS = ["<5 MW", "5-10 MW", "10-50 MW", ">=50 MW"]


def detail_table(points: pd.DataFrame) -> pd.DataFrame:
    """Detections per year x satellite x country/adm1 x day/night x fire strength (FRP class).

    For the "why do satellites disagree" view: overpass time (day/night share) and
    sensitivity (share of weak fires) differ by satellite.
    """
    d = points[["solar_date", "satellite", "country", "adm1", "daynight", "frp"]].copy()
    d["year"] = pd.to_datetime(d["solar_date"]).dt.year.astype("int16")
    for c in ("country", "adm1"):
        d[c] = d[c].astype(object).where(d[c].notna(), "")
    d["frp_class"] = pd.cut(d["frp"].fillna(0).clip(lower=0), FRP_BINS, labels=FRP_LABELS, right=False).astype(str)
    d["daynight"] = d["daynight"].astype(str).str.upper().str[:1]
    return (d.groupby(["year", "satellite", "country", "adm1", "daynight", "frp_class"]).size()
            .rename("detections").reset_index())


def build_detail(points_dir: str | Path, out_dir: str | Path) -> Path:
    cols = ["solar_date", "satellite", "country", "adm1", "daynight", "frp"]
    parts = [detail_table(pd.read_parquet(f, columns=cols)) for f in sorted(Path(points_dir).glob("*.parquet"))]
    t = pd.concat(parts, ignore_index=True)
    t = t.groupby(list(t.columns[:-1]), as_index=False)["detections"].sum()
    out = Path(out_dir) / "detail_admin.parquet"
    t.to_parquet(out, index=False)
    return out


def load_daily(path: str | Path, countries: list[str] | None = None) -> pd.DataFrame:
    """Read a daily table; `countries` reads only their rows (the all-Asia grid is large)."""
    import pyarrow.parquet as pq

    names = pq.ParquetFile(path).schema_arrow.names
    flt = [("country", "in", list(countries))] if countries is not None and "country" in names else None
    # text columns as categories: the all-Asia grid has ~31 M rows
    t = pq.read_table(path, filters=flt,
                      read_dictionary=[c for c in ("satellite", *REGION_COLS) if c in names]).to_pandas()
    t["date"] = pd.to_datetime(t["date"])
    if "peat" not in t:  # tables built before the peat split
        t["peat"] = False
    if "gy" in t:
        t["key"] = t["gy"].astype("int64") * KEY_MULT + t["gx"].astype("int64")
    if "country" in t:
        for c in REGION_COLS:
            if isinstance(t[c].dtype, pd.CategoricalDtype):
                if "" in t[c].cat.categories:
                    t[c] = t[c].cat.remove_categories([""])  # "" (no region) -> missing
                if "gy" not in t:  # the small admin table: plain objects, as before
                    t[c] = t[c].astype(object).where(t[c].notna(), None)
            else:
                t[c] = t[c].astype(object).replace("", None)
    return t


# ----------------------------------------------------------------------------- areas
def cell_key(gy, gx):
    return np.asarray(gy, "int64") * KEY_MULT + np.asarray(gx, "int64")


def key_to_cell(keys) -> tuple[np.ndarray, np.ndarray]:
    keys = np.asarray(keys, "int64")
    gy = np.floor_divide(keys + KEY_MULT // 2, KEY_MULT)
    return gy, keys - gy * KEY_MULT


def box_cells(west: float, south: float, east: float, north: float, area_deg: float = AREA_DEG) -> np.ndarray:
    """Keys of area cells whose centre lies inside the box."""
    if east <= west or north <= south:
        raise ValueError("The box needs west < east and south < north")
    gy = np.arange(np.floor(south / area_deg), np.ceil(north / area_deg)).astype("int64")
    gx = np.arange(np.floor(west / area_deg), np.ceil(east / area_deg)).astype("int64")
    yy, xx = np.meshgrid(gy, gx, indexing="ij")
    cy, cx = (yy + 0.5) * area_deg, (xx + 0.5) * area_deg
    ok = (cy >= south) & (cy <= north) & (cx >= west) & (cx <= east)
    return np.sort(cell_key(yy[ok], xx[ok]))


def circle_cells(lat: float, lon: float, radius_km: float, area_deg: float = AREA_DEG) -> np.ndarray:
    """Keys of area cells whose centre lies within `radius_km` of (lat, lon)."""
    if radius_km <= 0:
        raise ValueError("The radius must be positive")
    dlat = radius_km / 111.32
    dlon = radius_km / (111.32 * max(np.cos(np.radians(lat)), 0.01))
    keys = box_cells(lon - dlon - area_deg, lat - dlat - area_deg, lon + dlon + area_deg, lat + dlat + area_deg, area_deg)
    gy, gx = key_to_cell(keys)
    cy, cx = (gy + 0.5) * area_deg, (gx + 0.5) * area_deg
    dist = haversine_km(lat, lon, cy, cx)
    keys = keys[dist <= radius_km]
    if len(keys) == 0:  # a small circle still covers the cell it sits in
        keys = cell_key([np.floor(lat / area_deg)], [np.floor(lon / area_deg)])
    return np.sort(keys)


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    dp, dl = p2 - p1, np.radians(np.asarray(lon2) - lon1)
    a = np.sin(dp / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(dl / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def cells_km2(keys, area_deg: float = AREA_DEG) -> float:
    gy, _ = key_to_cell(keys)
    lat = (gy + 0.5) * area_deg
    return float(np.sum((area_deg * 111.32) ** 2 * np.cos(np.radians(lat))))


def cells_geojson(keys, area_deg: float = AREA_DEG) -> dict:
    """The area as one GeoJSON MultiPolygon (dissolved cells), for drawing on a map."""
    import json

    import shapely

    gy, gx = key_to_cell(keys)
    boxes = shapely.box(gx * area_deg, gy * area_deg, (gx + 1) * area_deg, (gy + 1) * area_deg)
    geom = shapely.union_all(boxes)
    return {"type": "FeatureCollection",
            "features": [{"type": "Feature", "id": "area", "properties": {}, "geometry": json.loads(shapely.to_geojson(geom))}]}


def cells_extent(keys, area_deg: float = AREA_DEG) -> tuple[float, float, float, float]:
    gy, gx = key_to_cell(keys)
    return (float(gx.min() * area_deg), float(gy.min() * area_deg),
            float((gx.max() + 1) * area_deg), float((gy.max() + 1) * area_deg))


# ----------------------------------------------------------------------------- series
def daily_wide(rows: pd.DataFrame) -> pd.DataFrame:
    """date x satellite cell-days (only days with detections)."""
    if rows.empty:
        return pd.DataFrame(dtype=float)
    w = rows.groupby(["date", "satellite"], observed=True)["cell_days"].sum().unstack("satellite")
    w.columns = w.columns.astype(str)
    return w.fillna(0.0).astype(float).sort_index()


def _peat_sel(t: pd.DataFrame, peat: bool | None):
    return np.ones(len(t), bool) if peat is None else (t["peat"].to_numpy(bool) == bool(peat))


def daily_for_region(admin: pd.DataFrame, countries=None, adm1=None, adm2=None,
                     peat: bool | None = None) -> pd.DataFrame:
    """date x satellite cell-days; peat=True/False keeps only fires on / off mapped peat."""
    from .regions import as_isos

    countries = as_isos(countries)
    sel = admin["country"].isin(countries)
    if adm1:
        sel &= admin["adm1"].isin([adm1] if isinstance(adm1, str) else list(adm1))
    if adm2:
        sel &= admin["adm2"].isin([adm2] if isinstance(adm2, str) else list(adm2))
    return daily_wide(admin[sel & _peat_sel(admin, peat)])


def grid_for_region(grid: pd.DataFrame, countries=None, adm1=None, adm2=None) -> pd.DataFrame:
    """Rows of the daily grid inside a listed region (grid built with region columns)."""
    from .regions import as_isos

    sel = grid["country"].isin(as_isos(countries))
    if adm1:
        sel &= grid["adm1"].isin([adm1] if isinstance(adm1, str) else list(adm1))
    if adm2:
        sel &= grid["adm2"].isin([adm2] if isinstance(adm2, str) else list(adm2))
    return grid[sel]


def daily_for_cells(grid: pd.DataFrame, keys, peat: bool | None = None) -> pd.DataFrame:
    return daily_wide(grid[grid["key"].isin(np.asarray(keys, "int64")) & _peat_sel(grid, peat)])


def monthly_from_daily(daily: pd.DataFrame, coverage: dict[str, tuple[str, str]]) -> pd.DataFrame:
    """Monthly cell-days per satellite, NaN outside each satellite's record, 0 inside it
    (same convention as cube.monthly_from_cube)."""
    lo = min(pd.Period(c[0], "M") for c in coverage.values())
    hi = max(pd.Period(c[1], "M") for c in coverage.values())
    idx = pd.period_range(lo, hi, freq="M")
    m = daily.groupby(daily.index.to_period("M")).sum() if len(daily) else pd.DataFrame(index=idx[:0])
    out = pd.DataFrame(index=idx)
    for sat, (a, b) in coverage.items():
        col = m[sat].reindex(idx) if sat in m else pd.Series(np.nan, index=idx)
        inside = (idx >= pd.Period(a, "M")) & (idx <= pd.Period(b, "M"))
        out[sat] = col.fillna(0.0).where(inside)
    out.index.name = "month"
    return out


def last_complete_day(daily_all: pd.DataFrame, satellite: str = "NOAA20", lookback: int = 14,
                      min_share: float = 0.5) -> pd.Timestamp:
    """Last day whose count looks complete. The newest day is often only partly downloaded
    (later passes not yet in FIRMS); it is dropped if it has less than `min_share` of the
    median of the previous `lookback` days."""
    s = daily_all[satellite] if satellite in daily_all else daily_all.sum(axis=1)
    s = s[s > 0]
    last = s.index.max()
    prev = s.loc[last - pd.Timedelta(days=lookback): last - pd.Timedelta(days=1)]
    if len(prev) and s.loc[last] < min_share * prev.median():
        return last - pd.Timedelta(days=1)
    return last


# ----------------------------------------------------------------------------- date windows
def _sources(src: str) -> list[str]:
    """Satellites a harmonized month was measured or converted from ('Aqua+Terra converted ...')."""
    return src.split(" ")[0].split("+")


def window_totals(frame: pd.DataFrame, daily: pd.DataFrame, start, end, last_day) -> pd.DataFrame:
    """Harmonized total (with likely range) for the window [start, end] shifted to every year.

    Each overlapped month contributes its harmonized value times the share of that month's
    raw cell-days (from the month's source satellites) that falls inside the window. Years
    where a needed month is missing, or where the window runs past `last_day`, are left out.
    Rows are labelled by the year the shifted window ends in.
    """
    start, end, last_day = pd.Timestamp(start).normalize(), pd.Timestamp(end).normalize(), pd.Timestamp(last_day)
    if end < start:
        raise ValueError("The end date is before the start date")
    if (end - start).days > 365:
        raise ValueError("Choose at most one year")
    first_month = frame["harmonized"].dropna().index.min()
    rows = []
    for k in range(-40, 1):
        s, e = start + pd.DateOffset(years=k), end + pd.DateOffset(years=k)
        if e > last_day or pd.Period(s, "M") < first_month:
            continue
        tot = lo = hi = 0.0
        est, ok = False, True
        for m in pd.period_range(pd.Period(s, "M"), pd.Period(e, "M"), freq="M"):
            if m not in frame.index or pd.isna(frame.at[m, "harmonized"]):
                ok = False
                break
            src = frame.at[m, "source"]
            sats = [x for x in _sources(src) if x in daily.columns]
            m0, m1 = m.start_time, min(m.end_time.normalize(), last_day)
            w0, w1 = max(s, m0), min(e, m1)
            if sats:
                month_raw = daily.loc[m0:m1, sats].to_numpy().sum()
                win_raw = daily.loc[w0:w1, sats].to_numpy().sum()
            else:
                month_raw = win_raw = 0.0
            share = (win_raw / month_raw) if month_raw > 0 else ((w1 - w0).days + 1) / ((m1 - m0).days + 1)
            tot += frame.at[m, "harmonized"] * share
            lo += frame.at[m, "lower"] * share
            hi += frame.at[m, "upper"] * share
            est |= not src.endswith("measured")
        if ok:
            rows.append({"year": int(e.year), "start": s.date(), "end": e.date(), "total": tot,
                         "lower": lo, "upper": hi, "estimated": est})
    return pd.DataFrame(rows).set_index("year") if rows else pd.DataFrame(
        columns=["start", "end", "total", "lower", "upper", "estimated"])


def compare_window(totals: pd.DataFrame, year: int) -> dict:
    """Target year vs the median of every other year for the same dates."""
    if year not in totals.index:
        return {}
    others = totals.drop(index=year)["total"]
    med = float(others.median()) if len(others) else np.nan
    t = totals.loc[year]
    rank = int((totals["total"] > t["total"]).sum() + 1)
    return {"year": year, "total": float(t["total"]), "lower": float(t["lower"]), "upper": float(t["upper"]),
            "median": med, "pct_vs_median": float(100 * (t["total"] / med - 1)) if med and med > 0 else np.nan,
            "rank": rank, "n_years": int(len(totals)), "first_year": int(totals.index.min()),
            "estimated": bool(t["estimated"]),
            "range_includes_median": bool(t["lower"] <= med <= t["upper"]) if np.isfinite(med) else False}
