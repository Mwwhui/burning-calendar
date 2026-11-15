"""Load NASA FIRMS hotspot CSVs into one standard table, or generate demo data.

Standard columns (STANDARD_COLUMNS):
    latitude, longitude, acq_date (datetime64, UTC date), acq_time (int HHMM UTC),
    satellite (Terra/Aqua/SNPP/NOAA20/NOAA21), sensor (MODIS/VIIRS),
    product (SP = standard/archive, NRT = near real time), confidence (str),
    frp, daynight, type (float; NaN when the file has no type column, e.g. NRT)
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import numpy as np
import pandas as pd

from .config import PLATFORMS, SENSOR_OF

log = logging.getLogger(__name__)

STANDARD_COLUMNS = [
    "latitude", "longitude", "acq_date", "acq_time", "satellite", "sensor",
    "product", "confidence", "frp", "daynight", "type",
]

SATELLITE_ALIASES = {
    "terra": "Terra", "t": "Terra", "aqua": "Aqua", "a": "Aqua",
    "n": "SNPP", "npp": "SNPP", "snpp": "SNPP", "suomi npp": "SNPP", "suomi-npp": "SNPP",
    "n20": "NOAA20", "noaa-20": "NOAA20", "noaa20": "NOAA20", "noaa 20": "NOAA20", "j1": "NOAA20", "1": "NOAA20",
    "n21": "NOAA21", "noaa-21": "NOAA21", "noaa21": "NOAA21", "noaa 21": "NOAA21", "j2": "NOAA21", "2": "NOAA21",
}

# Substrings in FIRMS file names (archive: fire_archive_SV-C2_*, fire_nrt_J1V-C2_*, ...)
FILENAME_HINTS = [
    ("j2v", "NOAA21"), ("noaa21", "NOAA21"), ("noaa-21", "NOAA21"), ("jpss2", "NOAA21"),
    ("j1v", "NOAA20"), ("noaa20", "NOAA20"), ("noaa-20", "NOAA20"), ("jpss1", "NOAA20"),
    ("sv-c2", "SNPP"), ("snpp", "SNPP"), ("suomi", "SNPP"),
]


def normalize_satellite(values: pd.Series) -> pd.Series:
    """Map FIRMS satellite codes ('A', 'Aqua', 'N', 'N20', '1', 'J2', ...) to platform names."""
    key = values.astype("string").str.strip().str.lower()
    # integer-like floats read from CSV ("1.0") -> "1"
    key = key.str.replace(r"\.0$", "", regex=True)
    return key.map(SATELLITE_ALIASES).astype(object)


def _hint_from_filename(path: str | os.PathLike) -> str | None:
    name = Path(path).name.lower()
    for token, platform in FILENAME_HINTS:
        if token in name:
            return platform
    return None


def standardize(df: pd.DataFrame, source_name: str = "") -> pd.DataFrame | None:
    """Return `df` in the standard schema, or None if it is not a FIRMS MODIS/VIIRS table."""
    df = df.copy()
    df.columns = [str(c).strip().lower() for c in df.columns]
    if "bright_ti4" in df.columns:
        sensor = "VIIRS"
    elif "brightness" in df.columns:
        sensor = "MODIS"
    else:
        return None

    out = pd.DataFrame(index=df.index)
    out["latitude"] = pd.to_numeric(df["latitude"], errors="coerce")
    out["longitude"] = pd.to_numeric(df["longitude"], errors="coerce")
    out["acq_date"] = pd.to_datetime(df["acq_date"], errors="coerce")
    out["acq_time"] = pd.to_numeric(df["acq_time"], errors="coerce") if "acq_time" in df else np.nan

    sat = normalize_satellite(df["satellite"]) if "satellite" in df else pd.Series(None, index=df.index, dtype=object)
    hint = _hint_from_filename(source_name)
    if hint is not None:
        sat = sat.fillna(hint)
    out["satellite"] = sat
    out["sensor"] = sensor

    if "version" in df:
        out["product"] = np.where(df["version"].astype(str).str.upper().str.contains("NRT"), "NRT", "SP")
    else:
        out["product"] = "NRT" if "nrt" in Path(source_name).name.lower() else "SP"

    out["confidence"] = df["confidence"].astype(str).str.strip().str.lower() if "confidence" in df else np.nan
    out["frp"] = pd.to_numeric(df["frp"], errors="coerce") if "frp" in df else np.nan
    out["daynight"] = df["daynight"] if "daynight" in df else np.nan
    out["type"] = pd.to_numeric(df["type"], errors="coerce") if "type" in df else np.nan

    bad = out["satellite"].isna() | ~out["satellite"].isin(PLATFORMS)
    if bad.any():
        log.warning("%s: %d rows with unknown satellite dropped", source_name or "table", int(bad.sum()))
        out = out[~bad]
    wrong_sensor = out["satellite"].map(SENSOR_OF) != sensor
    if wrong_sensor.any():
        log.warning("%s: %d rows whose satellite does not match the %s columns dropped",
                    source_name or "table", int(wrong_sensor.sum()), sensor)
        out = out[~wrong_sensor]
    return out[STANDARD_COLUMNS].reset_index(drop=True)


def load_firms_csv(path: str | os.PathLike) -> pd.DataFrame | None:
    df = pd.read_csv(path, low_memory=False)
    return standardize(df, str(path))


def load_firms_folder(folder: str | os.PathLike) -> pd.DataFrame:
    """Load every FIRMS CSV under `folder` (recursively, skipping hidden dirs such as .cache).

    The same detection can appear in both SP and NRT files; SP is kept.
    """
    folder = Path(folder)
    files = sorted(
        p for p in folder.rglob("*.csv")
        if not any(part.startswith(".") for part in p.relative_to(folder).parts)
    )
    if not files:
        raise FileNotFoundError(
            f"No CSV files found in '{folder}'. Download FIRMS data there "
            "(scripts/download_firms.py or the FIRMS archive page), or use demo data."
        )
    frames = []
    for f in files:
        df = load_firms_csv(f)
        if df is None:
            log.info("Skipping %s: not a FIRMS MODIS/VIIRS file", f.name)
            continue
        log.info("Loaded %-45s %8d rows", f.name, len(df))
        frames.append(df)
    if not frames:
        raise ValueError(f"No FIRMS MODIS/VIIRS tables found in '{folder}'.")
    raw = pd.concat(frames, ignore_index=True)
    raw = drop_nrt_overlap(raw)
    raw = raw.sort_values("product", key=lambda s: s.ne("SP"))  # SP first
    raw = raw.drop_duplicates(["satellite", "latitude", "longitude", "acq_date", "acq_time"], keep="first")
    return raw.sort_values(["acq_date", "acq_time"]).reset_index(drop=True)


def drop_nrt_overlap(raw: pd.DataFrame) -> pd.DataFrame:
    """Drop NRT rows on dates that the same satellite's SP (standard) record already covers.

    NRT and SP versions of one detection can differ slightly in position/time, so exact
    de-duplication misses them and they would be double counted.
    """
    sp_last = raw.loc[raw["product"] == "SP"].groupby("satellite")["acq_date"].max()
    last = raw["satellite"].map(sp_last)
    overlap = raw["product"].eq("NRT") & last.notna() & (raw["acq_date"] <= last)
    if overlap.any():
        log.info("Dropped %d NRT rows already covered by SP", int(overlap.sum()))
    return raw[~overlap]


# --------------------------------------------------------------------------- demo data

DEMO_SPANS = {
    "Terra": ("2000-11", None),
    "Aqua": ("2002-07", "2026-08"),
    "SNPP": ("2012-01", "2026-10"),
    "NOAA20": ("2018-04", None),
    "NOAA21": ("2024-01", None),
}
DEMO_RATE = {"Terra": 0.85, "Aqua": 1.0, "SNPP": 4.0, "NOAA20": 3.8, "NOAA21": 3.9}
DEMO_LOCAL_HOURS = {  # (day, night) local overpass, decimal hours
    "Terra": (10.5, 22.5), "Aqua": (13.5, 1.5), "SNPP": (13.5, 1.5),
    "NOAA20": (12.7, 0.7), "NOAA21": (13.1, 1.1),
}
DEMO_BAD_YEARS = {2002: 2.0, 2006: 2.2, 2009: 1.6, 2015: 3.0, 2019: 2.4, 2023: 1.8}


def make_demo_data(seed: int = 42, start: str = "2000-11", end: str = "2026-10",
                   scale: float = 1.0, aqua_drift: bool = True) -> pd.DataFrame:
    """Synthetic FIRMS-like hotspots in the standard schema. NOT real data.

    One latent fire level per month is seen by every platform active that month.
    VIIRS sees ~4x MODIS, more so in the low season (small fires). With `aqua_drift`
    Aqua's detections fall 6 %/year after 2021 to mimic its overpass drift.
    """
    rng = np.random.default_rng(seed)
    months = pd.period_range(start, end, freq="M")
    frames = []
    for p in months:
        season = 1 + 2.5 * np.exp(-((p.month - 8.5) ** 2) / 3.0) + 0.8 * np.exp(-((p.month - 2.5) ** 2) / 1.5)
        level = 60 * scale * season * DEMO_BAD_YEARS.get(p.year, 1.0) * rng.lognormal(0, 0.25)
        for plat, (a, b) in DEMO_SPANS.items():
            if p < pd.Period(a, "M") or (b is not None and p > pd.Period(b, "M")):
                continue
            ratio = DEMO_RATE[plat]
            if SENSOR_OF[plat] == "VIIRS" and season < 2:
                ratio *= 1.4
            if plat == "Aqua" and aqua_drift and p.year > 2021:
                ratio *= 0.94 ** (p.year - 2021)
            n = rng.poisson(level * ratio)
            if n == 0:
                continue
            lat = rng.uniform(1, 7, n)
            lon = rng.uniform(100, 119, n)
            day = rng.integers(1, p.days_in_month + 1, n)
            is_day = rng.random(n) < 0.8
            hours = np.where(is_day, DEMO_LOCAL_HOURS[plat][0], DEMO_LOCAL_HOURS[plat][1]) + rng.normal(0, 0.2, n)
            local = pd.to_datetime(dict(year=p.year, month=p.month, day=day)) + pd.to_timedelta(hours * 3600, unit="s")
            utc = local - pd.to_timedelta(lon / 15 * 3600, unit="s")
            if SENSOR_OF[plat] == "MODIS":
                conf = rng.integers(20, 101, n).astype(str)
            else:
                conf = rng.choice(np.array(["l", "n", "h"]), n, p=[0.1, 0.7, 0.2])
            frames.append(pd.DataFrame({
                "latitude": lat, "longitude": lon,
                "acq_date": utc.dt.normalize(),
                "acq_time": (utc.dt.hour * 100 + utc.dt.minute).astype(int),
                "satellite": plat, "sensor": SENSOR_OF[plat], "product": "SP",
                "confidence": conf,
                "frp": rng.exponential(25 if SENSOR_OF[plat] == "MODIS" else 8, n),
                "daynight": np.where(is_day, "D", "N"),
                "type": np.where(rng.random(n) < 0.01, 2.0, 0.0),
            }))
    return pd.concat(frames, ignore_index=True)[STANDARD_COLUMNS]
