"""Fine playback cells: where inside an area the fire actually was, at ~2 km.

The playback map (burncal.playback) spreads each period's harmonized total over 0.1° cells.
At state and district zoom those cells form a visible regular lattice. This module keeps the
same rule (the harmonized total of a period is shared out in proportion to raw cell-days) but

  * counts the raw cell-days in 0.02° cells (~2 km), and
  * remembers the mean position of the detections inside each cell,

so a dot can be drawn where the satellites saw fire, not at a grid-cell centre. Nothing is
invented: positions are averages of real detections, and the values still add up to the
area's harmonized total for the period.

The pattern inside a year comes from one satellite group (the most detailed one that flew
the whole year): Terra+Aqua before 2012, Suomi NPP 2012-2018, NOAA-20 from 2019. Month
frames use NOAA-20. Totals are not affected by this choice, only where they are drawn.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

FINE_DEG = 0.02  # fine cell (~2.2 km)
COUNT_DEG = 0.01  # counting cell for cell-days, as in the cube
DISPLAY_DEGS = (0.02, 0.05, 0.1, 0.25, 0.5, 1.0)


def pattern_satellites(year: int) -> tuple[str, ...]:
    """Satellites whose detections give the pattern of a year frame."""
    if year < 2012:
        return ("Terra", "Aqua")
    if year <= 2018:
        return ("SNPP",)
    return ("NOAA20",)


def fine_table(points: pd.DataFrame) -> pd.DataFrame:
    """Cleaned detections -> cell-days per (satellite, year, month, adm1, adm2, fine cell),
    with the sum of detection positions for centroids.

    points: latitude, longitude, solar_date, satellite, adm1, adm2.
    Columns out: satellite, year, month, adm1, adm2, fy, fx, cd (cell-days), n (detections),
    slat, slon (sums of detection latitude / longitude).
    """
    cols = ["satellite", "year", "month", "adm1", "adm2", "fy", "fx", "cd", "n", "slat", "slon"]
    if points.empty:
        return pd.DataFrame(columns=cols)
    p = points[["latitude", "longitude", "solar_date", "satellite", "adm1", "adm2"]].copy()
    p["adm1"] = p["adm1"].fillna("").astype(str)
    p["adm2"] = p["adm2"].fillna("").astype(str)
    p["day"] = pd.to_datetime(p["solar_date"]).dt.normalize()
    p["cy"] = np.floor(p["latitude"].to_numpy() / COUNT_DEG).astype("int64")
    p["cx"] = np.floor(p["longitude"].to_numpy() / COUNT_DEG).astype("int64")
    # one row per cell-day (as the cube counts), keeping detection count and position sums
    cd = p.groupby(["satellite", "day", "cy", "cx", "adm1", "adm2"], observed=True).agg(
        n=("latitude", "size"), slat=("latitude", "sum"), slon=("longitude", "sum")).reset_index()
    f = int(round(FINE_DEG / COUNT_DEG))
    cd["fy"] = np.floor_divide(cd["cy"], f).astype("int32")
    cd["fx"] = np.floor_divide(cd["cx"], f).astype("int32")
    cd["year"] = cd["day"].dt.year.astype("int16")
    cd["month"] = cd["day"].dt.month.astype("int8")
    out = cd.groupby(["satellite", "year", "month", "adm1", "adm2", "fy", "fx"], observed=True).agg(
        cd=("n", "size"), n=("n", "sum"), slat=("slat", "sum"), slon=("slon", "sum")).reset_index()
    out["cd"] = out["cd"].astype("int32")
    out["n"] = out["n"].astype("int32")
    return out[cols]


def choose_deg(fine: pd.DataFrame, max_cells: int = 15_000) -> float:
    """Coarsest-needed display cell so no frame has more than `max_cells` dots."""
    if fine.empty:
        return FINE_DEG
    for deg in DISPLAY_DEGS:
        k = int(round(deg / FINE_DEG))
        per = fine.assign(dy=fine["fy"] // k, dx=fine["fx"] // k).groupby("year")[["dy", "dx"]].apply(
            lambda g: len(g.drop_duplicates()))
        if per.max() <= max_cells:
            return deg
    return DISPLAY_DEGS[-1]


def fine_frames(frame: pd.DataFrame, fine: pd.DataFrame, step: str = "year", deg: float | None = None,
                month_years: int = 3) -> pd.DataFrame:
    """Harmonized fire days per display cell and period, drawn at the detections' mean position.

    frame: HarmonizationResult.frame (harmonized per month). fine: fine_table rows of the area.
    step "year": every year, pattern from pattern_satellites(year); "month": the latest
    `month_years` years, pattern from NOAA-20. Returns period, lat, lon, value, plus attrs
    {"deg", "totals" (period -> harmonized total)}; values add up to the totals.
    """
    h = frame["harmonized"].dropna()
    empty = pd.DataFrame(columns=["period", "lat", "lon", "value"])
    if h.empty or fine.empty:
        return empty
    deg = deg or choose_deg(fine)
    k = int(round(deg / FINE_DEG))
    g = fine.assign(dy=fine["fy"] // k, dx=fine["fx"] // k)
    if step == "year":
        totals = h.groupby(h.index.year).sum()
        keep = np.zeros(len(g), bool)
        for y in totals.index:
            keep |= (g["year"] == y).to_numpy() & g["satellite"].isin(pattern_satellites(int(y))).to_numpy()
        g = g[keep]
        g = g.assign(period=[str(int(v)) for v in g["year"].to_numpy()])
        totals.index = totals.index.astype(str)
    else:
        last = h.index.max()
        hm = h[h.index.year > last.year - month_years]
        g = g[(g["satellite"] == "NOAA20") & (g["year"] > last.year - month_years)]
        ym = g["year"].to_numpy().astype(int) * 100 + g["month"].to_numpy().astype(int)
        g = g.assign(period=[f"{v // 100}-{v % 100:02d}" for v in ym])
        totals = pd.Series(hm.to_numpy(), index=hm.index.astype(str))
    cells = g.groupby(["period", "dy", "dx"]).agg(cd=("cd", "sum"), n=("n", "sum"), slat=("slat", "sum"),
                                                   slon=("slon", "sum")).reset_index()
    cells = cells[cells["period"].isin(totals.index)]
    if cells.empty:
        return empty
    share = cells["cd"] / cells.groupby("period")["cd"].transform("sum")
    out = pd.DataFrame({"period": cells["period"], "lat": cells["slat"] / cells["n"],
                        "lon": cells["slon"] / cells["n"],
                        "value": share * cells["period"].map(totals).to_numpy()})
    out = out.sort_values("period", kind="stable").reset_index(drop=True)
    out.attrs.update({"deg": deg, "totals": totals.loc[sorted(set(out["period"]))]})
    return out
