"""Static heat sources (gas flares, refineries, steel works, volcanoes): a mask for NRT data.

FIRMS archive (SP) files label each hotspot with `type`: 0 = presumed vegetation fire,
1 = active volcano, 2 = other static land source, 3 = offshore. NRT files (the newest
months) have no `type`, so without a mask a gas flare counts as a fire there and
"this month vs the median" is inflated.

The mask is learned from the labels themselves: a ~1 km counting cell (the cube's
`grid_deg` grid) is static if VIIRS archive detections inside it were labelled 1/2/3 at
least `min_labels` times (default 1). VIIRS only, because its 375 m pixels place a flare in the right
1 km cell; MODIS (1 km) smears it over neighbours.

The mask is applied to every satellite and every year, not only to NRT rows. A cell
that hosts a flare also loses its few real fires, but it loses them in all years alike,
so the calendar stays consistent from 2000 to today and only the newest months change.

Tested on held-out years (mask from earlier years only, `docs/decisions.md`), min_labels=1:
Southeast Asia 2025: 96.9 % of labelled static detections caught, 0.76 % of vegetation fires removed;
2026 (Southeast Asian tiles): 94.6 % caught, 0.87 % removed (min_labels=3: 93.3 %, 0.56 %).
All Asia: 2025 97.9 % caught, 3.8 % of unlabelled detections removed, mostly unlabelled
flares (most sit in squares burning on >= 10 days a year).
What matters for the headline is the bias left in NRT months. Simulated on May-Jul 2026
archive months treated as NRT (labels hidden, mask from data up to April 2026), in fire
days: no mask +29 to +49 % (Malaysia box), mask with 1 label +2 %, with 3 labels +3-4 %.
The fires the mask removes are removed in every year alike, so they do not bias
comparisons; hence the lower threshold. A rule without labels ("same cell burns in >= N
years") fails here: farms and peat burn in the same places every year (10+ years: 56 %
caught but 29 % of real fires removed).
"""

from __future__ import annotations

import hashlib
from pathlib import Path

import numpy as np
import pandas as pd

STATIC_TYPES = (1, 2, 3)
MASK_COLS = ["cell_y", "cell_x", "n_static", "n_veg", "first_year", "last_year"]


def _cells(lat, lon, grid_deg: float) -> tuple[np.ndarray, np.ndarray]:
    return (np.floor(np.asarray(lat, float) / grid_deg).astype("int64"),
            np.floor(np.asarray(lon, float) / grid_deg).astype("int64"))


def label_counts(frames, grid_deg: float = 0.01) -> pd.DataFrame:
    """Per cell: detections labelled static / vegetation and the years of static labels.

    frames: iterable of DataFrames with latitude, longitude, acq_date and type (VIIRS SP
    rows; rows without a type are ignored).
    """
    parts = []
    for d in frames:
        d = d[d["type"].notna()]
        if d.empty:
            continue
        gy, gx = _cells(d["latitude"], d["longitude"], grid_deg)
        st = d["type"].astype(int).isin(STATIC_TYPES).to_numpy()
        year = pd.to_datetime(d["acq_date"]).dt.year.to_numpy()
        parts.append(pd.DataFrame({"cell_y": gy, "cell_x": gx, "static": st, "year": year}))
    if not parts:
        return pd.DataFrame(columns=MASK_COLS)
    a = pd.concat(parts, ignore_index=True)
    g = a.groupby(["cell_y", "cell_x"])
    out = pd.DataFrame({"n_static": g["static"].sum(), "n_veg": g["static"].size() - g["static"].sum()})
    yrs = a[a["static"]].groupby(["cell_y", "cell_x"])["year"].agg(["min", "max"])
    out = out[out["n_static"] > 0].join(yrs.rename(columns={"min": "first_year", "max": "last_year"}))
    return out.reset_index()[MASK_COLS].astype("int64")


def static_cells(counts: pd.DataFrame, min_labels: int = 1) -> pd.DataFrame:
    return counts[counts["n_static"] >= min_labels].reset_index(drop=True)


def mask_id(mask: pd.DataFrame) -> str:
    """Short fingerprint of a mask, so a cube built with another mask is not mixed in."""
    keys = np.sort(mask["cell_y"].to_numpy("int64") * 1_000_000 + mask["cell_x"].to_numpy("int64"))
    return f"{len(keys)}:{hashlib.md5(keys.tobytes()).hexdigest()[:10]}"


def in_mask(df: pd.DataFrame, mask: pd.DataFrame, grid_deg: float = 0.01) -> np.ndarray:
    """Boolean array: is each hotspot inside a static cell?"""
    if df.empty or mask.empty:
        return np.zeros(len(df), bool)
    gy, gx = _cells(df["latitude"], df["longitude"], grid_deg)
    keys = gy * 1_000_000 + gx
    mkeys = mask["cell_y"].to_numpy("int64") * 1_000_000 + mask["cell_x"].to_numpy("int64")
    return np.isin(keys, mkeys)


def drop_static(df: pd.DataFrame, mask: pd.DataFrame | None, grid_deg: float = 0.01) -> pd.DataFrame:
    if mask is None or df.empty:
        return df
    return df[~in_mask(df, mask, grid_deg)]


def load_mask(path: str | Path) -> pd.DataFrame:
    return pd.read_parquet(path)[MASK_COLS]
