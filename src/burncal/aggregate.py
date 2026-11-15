"""Local solar dates, grid cells and monthly counts per platform.

Why local solar time: FIRMS `acq_date`/`acq_time` are UTC. In Malaysia (UTC+7/8 by
longitude) the ~01:30 night pass falls on the previous UTC day, so counting cell-days
by UTC date splits one local night across two days. Solar time = UTC + longitude/15 h.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .config import PLATFORMS


def add_solar_date(df: pd.DataFrame) -> pd.DataFrame:
    """Add `solar_date` (local solar calendar date). Falls back to acq_date when acq_time is missing."""
    out = df.copy()
    t = pd.to_numeric(out["acq_time"], errors="coerce")
    minutes = (t // 100) * 60 + (t % 100)
    utc = out["acq_date"] + pd.to_timedelta(minutes.fillna(0) * 60, unit="s")
    solar = utc + pd.to_timedelta(out["longitude"] / 15 * 3600, unit="s")
    out["solar_date"] = solar.dt.normalize().where(t.notna(), out["acq_date"].dt.normalize())
    return out


def add_cells(df: pd.DataFrame, grid_deg: float) -> pd.DataFrame:
    out = df.copy()
    out["cell_y"] = np.floor(out["latitude"] / grid_deg).astype("int64")
    out["cell_x"] = np.floor(out["longitude"] / grid_deg).astype("int64")
    return out


def monthly_counts(df: pd.DataFrame, unit: str = "cell_days", grid_deg: float = 0.01,
                   by: str = "satellite",
                   coverage: dict[str, tuple[str, str | None]] | None = None) -> pd.DataFrame:
    """Monthly counts with one column per value of `by` (default: platform).

    unit="cell_days": each grid cell counts once per local solar day per column.
    unit="points": raw hotspot count.
    Months outside a column's coverage are NaN; inside it, months with no detections are 0.
    Coverage defaults to the first..last month that column has data; override with
    `coverage={"SNPP": ("2012-01", "2026-11")}` when a platform's real record is longer
    than its detections in a small region.
    """
    if unit not in {"cell_days", "points"}:
        raise ValueError("unit must be 'cell_days' or 'points'")
    d = add_solar_date(df) if "solar_date" not in df else df.copy()
    d["month"] = d["solar_date"].dt.to_period("M")
    if unit == "cell_days":
        d = add_cells(d, grid_deg).drop_duplicates([by, "cell_y", "cell_x", "solar_date"])

    counts = d.groupby(["month", by]).size().unstack(by)
    full = pd.period_range(d["month"].min(), d["month"].max(), freq="M")
    counts = counts.reindex(full).astype(float)
    counts.index.name = "month"
    coverage = coverage or {}
    for col in counts.columns:
        if col in coverage:
            a, b = coverage[col]
            first = pd.Period(a, "M")
            last = pd.Period(b, "M") if b else full.max()
        else:
            m = d.loc[d[by] == col, "month"]
            first, last = m.min(), m.max()
        inside = (counts.index >= first) & (counts.index <= last)
        counts.loc[inside, col] = counts.loc[inside, col].fillna(0)
        counts.loc[~inside, col] = np.nan

    order = [p for p in PLATFORMS if p in counts.columns] + [c for c in counts.columns if c not in PLATFORMS]
    counts = counts[order]
    counts.columns.name = None
    return counts


def satellites_active(monthly: pd.DataFrame, platforms) -> pd.Series:
    """Number of the given platforms with data in each month (shown in the Method tab)."""
    cols = [p for p in platforms if p in monthly.columns]
    return monthly[cols].notna().sum(axis=1).astype(int)
