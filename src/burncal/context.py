"""Climate context: NOAA Oceanic Nino Index (ONI) and El Nino labels.

ONI = 3-month running mean of Nino 3.4 SST anomalies (NOAA CPC). Each season (DJF,
JFM, ...) is assigned to its centre month (DJF -> January).
CPC episode rule: El Nino when ONI >= +0.5 for at least 5 consecutive overlapping
seasons; La Nina when ONI <= -0.5 for 5.
For fire calendars a simpler year label is also provided: a year is an "El Nino year"
when the mean ONI over the regional fire season is >= threshold (default Jul-Oct,
Southeast Asia's main burning season in Sumatra/Borneo).
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

SEASON_CENTER = {"DJF": 1, "JFM": 2, "FMA": 3, "MAM": 4, "AMJ": 5, "MJJ": 6,
                 "JJA": 7, "JAS": 8, "ASO": 9, "SON": 10, "OND": 11, "NDJ": 12}
DEFAULT_ONI = Path(__file__).resolve().parents[2] / "data" / "external" / "oni.ascii.txt"


def load_oni(path: str | Path | None = None) -> pd.Series:
    """Monthly ONI anomaly with a PeriodIndex (centre month of each 3-month season)."""
    p = Path(path) if path else DEFAULT_ONI
    if not p.exists():
        raise FileNotFoundError(f"{p} not found. Run: python scripts/download_context.py")
    df = pd.read_csv(p, sep=r"\s+")
    df.columns = [c.upper() for c in df.columns]
    months = df["SEAS"].map(SEASON_CENTER)
    if months.isna().any():
        raise ValueError(f"Unknown season codes: {sorted(set(df.loc[months.isna(), 'SEAS']))}")
    idx = pd.PeriodIndex([pd.Period(year=int(y), month=int(m), freq="M") for y, m in zip(df["YR"], months)])
    return pd.Series(df["ANOM"].to_numpy(float), index=idx, name="oni").sort_index()


def _runs(mask: np.ndarray, min_run: int) -> np.ndarray:
    """True where `mask` is part of a run of at least `min_run` consecutive Trues."""
    out = np.zeros(len(mask), bool)
    i = 0
    while i < len(mask):
        if mask[i]:
            j = i
            while j < len(mask) and mask[j]:
                j += 1
            if j - i >= min_run:
                out[i:j] = True
            i = j
        else:
            i += 1
    return out


def enso_phase(oni: pd.Series, threshold: float = 0.5, min_run: int = 5) -> pd.Series:
    """"El Nino" / "La Nina" / "Neutral" per month using the CPC 5-season rule."""
    v = oni.to_numpy(float)
    phase = np.full(len(v), "Neutral", dtype=object)
    phase[_runs(v >= threshold, min_run)] = "El Nino"
    phase[_runs(v <= -threshold, min_run)] = "La Nina"
    return pd.Series(phase, index=oni.index, name="enso_phase")


def enso_by_year(oni: pd.Series, months=(7, 8, 9, 10), threshold: float = 0.5) -> pd.DataFrame:
    """Mean ONI over the fire-season `months` per year, labelled El Nino / La Nina / Neutral.

    Years whose season months are not all available are flagged `complete=False`.
    """
    sel = oni[np.isin(oni.index.month, months)]
    g = sel.groupby(sel.index.year)
    out = pd.DataFrame({"season_oni": g.mean(), "complete": g.size() == len(months)})
    out["label"] = np.select([out["season_oni"] >= threshold, out["season_oni"] <= -threshold],
                             ["El Nino", "La Nina"], "Neutral")
    out.index.name = "year"
    return out


def el_nino_years(oni: pd.Series, months=(7, 8, 9, 10), threshold: float = 0.5) -> list[int]:
    t = enso_by_year(oni, months, threshold)
    return sorted(int(y) for y in t.index[t["label"] == "El Nino"])


DEFAULT_DMI = DEFAULT_ONI.parent / "dmi.had.long.csv"
DEFAULT_ASMC = DEFAULT_ONI.parent / "asmc_reviews.csv"
ASMC_ARCHIVE = "https://asmc.asean.org/category/haze-review/"


def load_dmi(path: str | Path | None = None) -> pd.Series:
    """Monthly Indian Ocean Dipole Mode Index (NOAA PSL, HadISST), missing months dropped."""
    p = Path(path) if path else DEFAULT_DMI
    if not p.exists():
        raise FileNotFoundError(f"{p} not found. Run: python scripts/download_context.py")
    d = pd.read_csv(p, skiprows=1, header=None, names=["date", "dmi"])
    d = d[pd.to_numeric(d["dmi"], errors="coerce") > -99]
    return pd.Series(d["dmi"].astype(float).to_numpy(), index=pd.PeriodIndex(pd.to_datetime(d["date"]), freq="M"),
                     name="dmi")


def asmc_reviews(path: str | Path | None = None) -> dict[pd.Period, list[tuple[str, str]]]:
    """ASEAN Specialised Meteorological Centre haze reviews per month: [(title, url)] (mid-2018 on)."""
    p = Path(path) if path else DEFAULT_ASMC
    if not p.exists():
        return {}
    t = pd.read_csv(p)
    out: dict[pd.Period, list[tuple[str, str]]] = {}
    for m, title, url in t[["month", "title", "url"]].itertuples(index=False):
        out.setdefault(pd.Period(m, "M"), []).append((title, url))
    return out
