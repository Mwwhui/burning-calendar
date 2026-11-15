"""Who is responsible for the land that burns: concessions and repeat burn spots.

Both work on the fine cells of burncal.fine (~2 km cells with the detections' mean position).

Concessions
    A fine cell belongs to a concession when the mean position of its detections lies inside
    the concession polygon. For each year, the share of the area's raw cell-days (from the
    year's pattern satellites, burncal.fine.pattern_satellites) that falls inside concessions
    is applied to the area's harmonized yearly total, the same like-for-like rule as the
    playback map. This-year-vs-typical per concession uses NOAA-20 only (no conversion).

Repeat burn spots
    A fine cell "burned" in a year when the year's VIIRS satellite (Suomi NPP 2012-2018,
    NOAA-20 from 2019) saw fire in it. Counting years from 2012 keeps one sensor family, so
    the count is not inflated by the switch from MODIS. Cells that burn in most years are
    usually farmland, plantations or recurring land clearing; the app says so and shows
    whether they lie on mapped peat or in a concession.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .fine import pattern_satellites

SPOTS_FIRST_YEAR = 2012  # first full VIIRS year


@dataclass
class Concession:
    id: int
    name: str
    group: str
    kind: str
    source: str
    geom: object  # shapely geometry
    km2: float


def _km2(geom) -> float:
    c = geom.centroid
    return float(geom.area * 111.32 ** 2 * np.cos(np.radians(c.y)))


def load_concessions(path: str | Path) -> list[Concession]:
    """Concession polygons from a GeoJSON (Sarawak oil palm layer fields: name, name_of_gr,
    concession, source_of)."""
    import shapely

    gj = json.loads(Path(path).read_text(encoding="utf-8"))
    out = []
    for i, f in enumerate(gj["features"]):
        if not f.get("geometry"):
            continue
        g = shapely.make_valid(shapely.from_geojson(json.dumps(f["geometry"])))
        p = f.get("properties") or {}
        name = (p.get("name_1") or p.get("name") or "").strip()
        if not name or name.lower().startswith("untitled"):
            name = f"Unnamed licence #{i + 1}"
        group = (p.get("name_of_gr") or "").strip()
        if group.lower() in ("other / unknown", "unknown", "other"):
            group = ""
        out.append(Concession(i, name, group, (p.get("concession") or "").strip(),
                              (p.get("source_of") or "").strip(), g, _km2(g)))
    return out


def assign_concessions(lat: np.ndarray, lon: np.ndarray, concessions: list[Concession]) -> np.ndarray:
    """Index of the concession holding each point (-1 = none; first match if they overlap)."""
    import shapely

    out = np.full(len(lat), -1, dtype=np.int32)
    if not concessions or len(lat) == 0:
        return out
    tree = shapely.STRtree([c.geom for c in concessions])
    pts = shapely.points(lon, lat)
    pi, gi = tree.query(pts, predicate="within")
    if len(pi) == 0:
        return out
    # first concession per point
    order = np.lexsort((gi, pi))
    pi, gi = pi[order], gi[order]
    first = np.r_[True, pi[1:] != pi[:-1]]
    out[pi[first]] = gi[first]
    return out


def cells_with_position(fine: pd.DataFrame) -> pd.DataFrame:
    """Fine rows with their detections' mean position (lat, lon)."""
    return fine.assign(lat=fine["slat"] / fine["n"], lon=fine["slon"] / fine["n"])


def concession_fire(fine: pd.DataFrame, conc_idx: np.ndarray, annual_totals: pd.Series,
                    n_concessions: int) -> dict:
    """Harmonized fire days inside concessions per year, overall and per concession.

    fine: fine rows of the area; conc_idx: concession index per row (-1 = outside);
    annual_totals: harmonized total per calendar year (current year so far).
    Returns {"years", "total", "inside", "per" (n_concessions x years)}.
    """
    f = fine.assign(conc=conc_idx)
    years = [int(y) for y in annual_totals.index if (f["year"] == y).any()]
    inside, per = [], np.zeros((n_concessions, len(years)))
    for j, y in enumerate(years):
        rows = f[(f["year"] == y) & f["satellite"].isin(pattern_satellites(y))]
        tot = rows["cd"].sum()
        if tot <= 0:
            inside.append(0.0)
            continue
        h = float(annual_totals.loc[y])
        by = rows[rows["conc"] >= 0].groupby("conc")["cd"].sum()
        per[by.index.to_numpy(), j] = h * by.to_numpy() / tot
        inside.append(h * by.sum() / tot)
    return {"years": years, "total": [float(annual_totals.loc[y]) for y in years], "inside": inside, "per": per}


def concession_change(fine: pd.DataFrame, conc_idx: np.ndarray, n_concessions: int, year: int, through_month: int,
                      base_years: list[int], min_base: float = 5.0) -> pd.DataFrame:
    """NOAA-20 fire days per concession in Jan..through_month of `year` vs the mean of the same
    months in `base_years` (as burncal's area change map). change_pct is NaN below `min_base`."""
    f = fine.assign(conc=conc_idx)
    f = f[(f["conc"] >= 0) & (f["satellite"] == "NOAA20") & (f["month"] <= through_month)]
    by = f.groupby(["conc", "year"])["cd"].sum().unstack(fill_value=0)
    idx = pd.RangeIndex(n_concessions)
    this = by[year].reindex(idx, fill_value=0) if year in by.columns else pd.Series(0, index=idx)
    base = by.reindex(columns=base_years, fill_value=0).mean(axis=1).reindex(idx, fill_value=0) if base_years \
        else pd.Series(np.nan, index=idx)
    out = pd.DataFrame({"this": this.astype(float), "typical": base.astype(float)})
    out["change_pct"] = (100 * (out["this"] / out["typical"] - 1)).where(out["typical"] >= min_base)
    return out


def repeat_spots(fine: pd.DataFrame, last_year: int, first_year: int = SPOTS_FIRST_YEAR) -> pd.DataFrame:
    """Per fine cell: in how many years a VIIRS satellite saw fire, which years (bit mask from
    `first_year`), the last year, cell-days, and the detections' mean position.

    Columns: fy, fx, lat, lon, years, mask, last, cd, this_year (fire in `last_year`).
    """
    sel = np.zeros(len(fine), bool)
    for y in range(first_year, last_year + 1):
        sel |= (fine["year"] == y).to_numpy() & fine["satellite"].isin(pattern_satellites(y)).to_numpy()
    f = fine[sel]
    if f.empty:
        return pd.DataFrame(columns=["fy", "fx", "lat", "lon", "years", "mask", "last", "cd", "this_year"])
    per_year = f.groupby(["fy", "fx", "year"]).agg(cd=("cd", "sum"), n=("n", "sum"), slat=("slat", "sum"),
                                                     slon=("slon", "sum")).reset_index()
    per_year["bit"] = np.left_shift(1, (per_year["year"].astype(int) - first_year)).astype("int64")
    g = per_year.groupby(["fy", "fx"]).agg(years=("year", "nunique"), mask=("bit", "sum"), last=("year", "max"),
                                           cd=("cd", "sum"), n=("n", "sum"), slat=("slat", "sum"),
                                           slon=("slon", "sum")).reset_index()
    g["lat"] = g["slat"] / g["n"]
    g["lon"] = g["slon"] / g["n"]
    g["this_year"] = g["last"] == last_year
    return g[["fy", "fx", "lat", "lon", "years", "mask", "last", "cd", "this_year"]]


def on_peat(lat: np.ndarray, lon: np.ndarray, peat_cells: pd.DataFrame | None, min_share: float = 0.5) -> np.ndarray:
    """True where the 0.01° cell of a point is mapped peat (burncal.peat convention: share >= 0.5)."""
    if peat_cells is None or len(lat) == 0:
        return np.zeros(len(lat), bool)
    peat = peat_cells[peat_cells["peat_share"] >= min_share]
    keys = set(zip(peat["cell_y"].to_numpy().tolist(), peat["cell_x"].to_numpy().tolist()))
    cy = np.floor(np.asarray(lat) / 0.01).astype(int)
    cx = np.floor(np.asarray(lon) / 0.01).astype(int)
    return np.array([(a, b) in keys for a, b in zip(cy.tolist(), cx.tolist())], dtype=bool)
