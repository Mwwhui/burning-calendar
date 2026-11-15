"""Playback map: harmonized burning activity, cell by cell, year by year (or month by month).

The harmonized record exists per area and month, not per map cell. To draw it on a map,
each month's harmonized total of the selected area is spread over the area's cells in
proportion to that month's raw detections from the satellite(s) the month was measured
or converted from (the same like-for-like shares used for date windows, burncal.daily).
So:
  - the cells of a frame add up exactly to the area's harmonized total for that period;
  - a cell's value in 2005 (from MODIS) and in 2020 (from NOAA-20) are both in
    NOAA-20-equivalent fire days, so the colours are comparable across the years;
  - the pattern inside a month comes from one satellite type, so in MODIS years small
    fires may be placed less precisely (1 km pixels, fewer small fires) than in VIIRS years.

Cells are 0.1 deg area cells, aggregated to a coarser display grid for big areas so the
animation stays light.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .daily import _sources


def display_deg(n_cells: int, max_cells: int = 12_000) -> float:
    """Coarsest-needed display grid: 0.1 deg when the area is small, up to 1 deg for all of Asia."""
    for deg, factor in ((0.1, 1), (0.25, 6.25), (0.5, 25), (1.0, 100)):
        if n_cells / factor <= max_cells:
            return deg
    return 1.0


def cell_frames(frame: pd.DataFrame, grid_rows: pd.DataFrame, step: str = "year",
                deg: float | None = None, area_deg: float = 0.1, last_day=None) -> pd.DataFrame:
    """Harmonized fire days per display cell and period.

    frame: HarmonizationResult.frame (harmonized, source per month).
    grid_rows: daily grid rows of the area (date, satellite, gy, gx, cell_days).
    step: "year" or "month". Returns columns period (str), lat, lon, value, plus attrs
    {"deg", "totals" (Series period -> total), "partial" (label of an unfinished last period)}.
    """
    h = frame["harmonized"].dropna()
    if h.empty or grid_rows.empty:
        return pd.DataFrame(columns=["period", "lat", "lon", "value"])
    g = grid_rows[["date", "satellite", "gy", "gx", "cell_days"]].copy()
    g["month"] = pd.to_datetime(g["date"]).dt.to_period("M")
    g["satellite"] = g["satellite"].astype(str)
    n_cells = g[["gy", "gx"]].drop_duplicates().shape[0]
    deg = deg or display_deg(n_cells)
    f = int(round(deg / area_deg))
    g["dy"] = np.floor_divide(g["gy"].astype("int64"), f)
    g["dx"] = np.floor_divide(g["gx"].astype("int64"), f)
    raw = g.groupby(["month", "satellite", "dy", "dx"], observed=True)["cell_days"].sum()
    parts = []
    for m, total in h.items():
        if m not in raw.index.get_level_values(0):
            continue
        sats = _sources(str(frame.at[m, "source"]))
        r = raw.loc[m]
        r = r[r.index.get_level_values("satellite").isin(sats)]
        if r.empty or r.sum() <= 0:
            continue
        cells = r.groupby(level=["dy", "dx"]).sum()
        parts.append(pd.DataFrame({"month": m, "dy": cells.index.get_level_values(0),
                                   "dx": cells.index.get_level_values(1),
                                   "value": total * cells.to_numpy() / cells.sum()}))
    if not parts:
        return pd.DataFrame(columns=["period", "lat", "lon", "value"])
    d = pd.concat(parts, ignore_index=True)
    if step == "year":
        d["period"] = d["month"].dt.year.astype(str)
        totals = h.groupby(h.index.year).sum()
        totals.index = totals.index.astype(str)
    else:
        d["period"] = d["month"].astype(str)
        totals = h.copy()
        totals.index = totals.index.astype(str)
    out = d.groupby(["period", "dy", "dx"], as_index=False)["value"].sum()
    out["lat"] = (out["dy"] + 0.5) * deg
    out["lon"] = (out["dx"] + 0.5) * deg
    out = out[["period", "lat", "lon", "value"]]
    last = h.index.max()
    partial = None
    if last_day is not None:
        ld = pd.Timestamp(last_day)
        if step == "year" and (ld.month, ld.day) != (12, 31) and str(ld.year) in set(out["period"]):
            partial = str(ld.year)
        elif step == "month" and ld.day != ld.days_in_month and str(last) in set(out["period"]):
            partial = str(last)
    out.attrs.update({"deg": deg, "totals": totals.loc[sorted(set(out["period"]))], "partial": partial})
    return out
