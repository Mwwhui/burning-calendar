"""Peat share of each ~1 km counting cell, from the CIFOR tropical peatland map.

Source: Gumbricht et al. (2017), Global Change Biology 23: 3581-3599; dataset
"Tropical and Subtropical Wetlands Distribution" v2.1, CIFOR, doi:10.17528/CIFOR/DATA.00058,
CC BY 4.0. Peat = >= 30 cm of organic soil (>= 50 % organic matter), mapped at ~231 m
from a hydrological model, soil moisture and landforms (2011). Known limits: mangroves are
counted as peat; SRTM errors over-map peat in places; 65 % agreement with 275 soil profiles.
So the split is "fires on mapped peat", not a field survey.

A hotspot is "on peat" when at least half of its 0.01 deg cell is mapped as peat.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

ASIA_BOX = (25.0, -11.2, 180.0, 40.0)  # west, south, east, north (Asia; the peat map ends at 40N)
DEFAULT_PEAT_TIF = Path(__file__).resolve().parents[2] / "data" / "external" / "peat" / "TROP-SUBTROP_PeatV21_2016_CIFOR.tif"
DEFAULT_PEAT_CELLS = Path(__file__).resolve().parents[2] / "data" / "external" / "peat_cells.parquet"
PEAT_SHARE = 0.5


def peat_cells_from_tif(tif: str | Path = DEFAULT_PEAT_TIF, box=ASIA_BOX, grid_deg: float = 0.01,
                        strip_rows: int = 500) -> pd.DataFrame:
    """Share of peat pixels in each grid cell inside `box` (cells with any peat only)."""
    import rasterio
    from rasterio.windows import Window, from_bounds

    w, s, e, n = box
    with rasterio.open(tif) as r:
        win = from_bounds(w, s, e, n, r.transform).round_offsets().round_lengths()
        win = win.intersection(Window(0, 0, r.width, r.height))  # the map ends at 40N / 180E
        t = r.transform
        cols = np.arange(win.col_off, win.col_off + win.width)
        lon = t.c + (cols + 0.5) * t.a
        gx = np.floor(lon / grid_deg).astype("int64")
        gx0 = gx.min()
        tot: dict[int, np.ndarray] = {}
        peat: dict[int, np.ndarray] = {}
        for r0 in range(int(win.row_off), int(win.row_off + win.height), strip_rows):
            nrow = min(strip_rows, int(win.row_off + win.height) - r0)
            a = r.read(1, window=Window(win.col_off, r0, win.width, nrow))
            nrow = a.shape[0]
            lat = t.f + (np.arange(r0, r0 + nrow) + 0.5) * t.e
            gy = np.floor(lat / grid_deg).astype("int64")
            valid = a <= 1  # 0 = not peat, 1 = peat; anything else is no data
            for y in np.unique(gy):
                rows = gy == y
                v, p = valid[rows], (a[rows] == 1)
                cnt = np.bincount(np.broadcast_to(gx - gx0, v.shape)[v], minlength=gx.max() - gx0 + 1)
                pc = np.bincount(np.broadcast_to(gx - gx0, p.shape)[p], minlength=gx.max() - gx0 + 1)
                tot[y] = tot.get(y, 0) + cnt
                peat[y] = peat.get(y, 0) + pc
    out = []
    for y in tot:
        idx = np.nonzero(peat[y])[0]
        if len(idx):
            out.append(pd.DataFrame({"cell_y": y, "cell_x": idx + gx0,
                                     "peat_share": peat[y][idx] / np.maximum(tot[y][idx], 1)}))
    return pd.concat(out, ignore_index=True) if out else pd.DataFrame(columns=["cell_y", "cell_x", "peat_share"])


def load_peat_cells(path: str | Path = DEFAULT_PEAT_CELLS) -> pd.DataFrame:
    return pd.read_parquet(path)


def on_peat(lat, lon, cells: pd.DataFrame, grid_deg: float = 0.01, share: float = PEAT_SHARE) -> np.ndarray:
    """Boolean array: is each point in a cell that is at least `share` mapped peat?"""
    gy = np.floor(np.asarray(lat, float) / grid_deg).astype("int64")
    gx = np.floor(np.asarray(lon, float) / grid_deg).astype("int64")
    c = cells[cells["peat_share"] >= share]
    return np.isin(gy * 1_000_000 + gx, c["cell_y"].to_numpy("int64") * 1_000_000 + c["cell_x"].to_numpy("int64"))


DEFAULT_PEAT_REGIONS = DEFAULT_PEAT_CELLS.parent / "peat_regions.parquet"


def peat_by_region(cells: pd.DataFrame, tagger=None, grid_deg: float = 0.01) -> pd.DataFrame:
    """Mapped peat area (km2) per country / adm1 / adm2, from the cell table (done once, it is slow)."""
    from .regions import RegionTagger

    tagger = tagger or RegionTagger()
    lat = (cells["cell_y"].to_numpy() + 0.5) * grid_deg
    lon = (cells["cell_x"].to_numpy() + 0.5) * grid_deg
    t = tagger.tag(pd.DataFrame({"latitude": lat, "longitude": lon}))
    km2 = cells["peat_share"].to_numpy() * (111.32 * grid_deg) ** 2 * np.cos(np.radians(lat))
    d = pd.DataFrame({"country": t["country"].fillna("").to_numpy(), "adm1": t["adm1"].fillna("").to_numpy(),
                      "adm2": t["adm2"].fillna("").to_numpy(), "km2": km2})
    return d.groupby(["country", "adm1", "adm2"], as_index=False)["km2"].sum()
