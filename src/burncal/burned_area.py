"""Independent check: GFED5 monthly burned area against the harmonized fire days.

GFED5 (Chen et al. 2023, AGU Advances; Zenodo doi:10.5281/zenodo.7668423, CC BY 4.0) maps
burned area from MODIS 500 m surface reflectance plus active-fire corrections for small
fires, 2001-2020 at 0.25 deg, in km2 per month, with a separate peat layer. It measures
burnt ground, not hot pixels, so it is a different method than ours; if both show the
same good and bad years and months, the harmonized record is not an artefact of satellite
changes. (Fire Harmony checks against MCD64A1 in the same spirit.)

Cells are given to a country/province by their centre point (0.25 deg = ~28 km), so only
countries and large provinces are compared.
"""

from __future__ import annotations

import io
import re
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
DEFAULT_GFED_ZIP = ROOT / "data" / "external" / "gfed5" / "BA.zip"
DEFAULT_GFED_REGIONS = ROOT / "data" / "external" / "gfed5_regions.parquet"
ASIA_BOX = (25.0, -11.2, 180.0, 82.0)
ARGENTINA_BOX = (-73.6, -55.2, -53.5, -21.7)  # scripts/download_firms.py ARGENTINA_BBOX
BOXES = (ASIA_BOX, ARGENTINA_BOX)


def _read_nc(data: bytes) -> dict[str, np.ndarray]:
    import h5py

    with h5py.File(io.BytesIO(data), "r") as f:
        out = {k: np.asarray(f[k][...]) for k in ("lat", "lon") if k in f}
        for k in ("Total", "Peat"):
            a = np.asarray(f[k][...], dtype="float64").squeeze()
            fill = f[k].attrs.get("_FillValue")
            if fill is not None:
                a[a == np.asarray(fill).item()] = np.nan
            out[k] = a
    return out


def build_gfed_regions(zip_path: str | Path = DEFAULT_GFED_ZIP, out: str | Path = DEFAULT_GFED_REGIONS,
                       tagger=None, boxes=BOXES) -> Path:
    """Monthly burned area (total and peat, km2) per country/adm1 for the study boxes (Asia, Argentina)."""
    from .regions import RegionTagger

    tagger = tagger or RegionTagger()
    z = zipfile.ZipFile(zip_path)
    # 0.25 deg monthly files only (1997-2000 are on a 1 deg grid)
    names = sorted(n for n in z.namelist() if re.search(r"BA(\d{6})\.nc$", n)
                   and int(re.search(r"BA(\d{4})", n).group(1)) >= 2001)
    cells: dict[int, tuple] = {}  # per box: (row index, column index, tagged cells)
    rows = []
    for name in names:
        ym = re.search(r"BA(\d{6})\.nc$", name).group(1)
        nc = _read_nc(z.read(name))
        lat, lon = nc["lat"], nc["lon"]
        if lat.ndim == 1 and nc["Total"].shape != (len(lat), len(lon)):
            raise ValueError(f"unexpected shape {nc['Total'].shape} in {name}")
        parts = []
        for b, (w, s, e, n) in enumerate(boxes):
            if b not in cells:
                iy = np.nonzero((lat >= s) & (lat <= n))[0]
                ix = np.nonzero((lon >= w) & (lon <= e))[0]
                yy, xx = np.meshgrid(lat[iy], lon[ix], indexing="ij")
                tagged = tagger.tag(pd.DataFrame({"latitude": yy.ravel(), "longitude": xx.ravel()}))
                cells[b] = (iy, ix, tagged[["country", "adm1"]].fillna("").reset_index(drop=True))
            iy, ix, c = cells[b]
            sub = lambda a: a[np.ix_(iy, ix)].ravel()  # noqa: E731
            parts.append(c.assign(total=sub(nc["Total"]), peat=sub(nc["Peat"])))
        d = pd.concat(parts, ignore_index=True)
        g = d.groupby(["country", "adm1"])[["total", "peat"]].sum().reset_index()
        g.insert(0, "month", f"{ym[:4]}-{ym[4:]}")
        rows.append(g)
    t = pd.concat(rows, ignore_index=True)
    t = t[t["country"] != ""]
    t.to_parquet(out, index=False)
    return Path(out)


def load_gfed_regions(path: str | Path = DEFAULT_GFED_REGIONS) -> pd.DataFrame:
    t = pd.read_parquet(path)
    t["month"] = pd.PeriodIndex(t["month"], freq="M")
    t["adm1"] = t["adm1"].replace("", None)
    return t


def gfed_monthly(t: pd.DataFrame, country: str | None = None, adm1: str | None = None) -> pd.DataFrame:
    """Monthly total and peat burned area (km2) for a country, list of countries (None = all Asia) / province."""
    from .regions import as_isos

    sel = t["country"].isin(as_isos(country))
    if adm1:
        sel &= t["adm1"] == adm1
    return t[sel].groupby("month")[["total", "peat"]].sum().sort_index()


def compare_burned_area(harmonized: pd.Series, gfed: pd.DataFrame) -> dict:
    """Agreement between harmonized fire days and GFED5 burned area, by month and by year.

    Correlations are on log(1 + x), so the many quiet months do not hide the big ones.
    The monthly correlation is also given with the average seasonal cycle removed
    (anomalies), which tests the year-to-year ups and downs rather than the calendar.
    """
    h, b = harmonized.dropna().align(gfed["total"], join="inner")
    lh, lb = np.log1p(h), np.log1p(b)
    ah = lh - lh.groupby(lh.index.month).transform("mean")
    ab = lb - lb.groupby(lb.index.month).transform("mean")
    yh, yb = h.groupby(h.index.year).sum(), b.groupby(b.index.year).sum()
    years = yh.index[h.groupby(h.index.year).size() == 12]
    yh, yb = yh.loc[years], yb.loc[years]
    rank = lambda s: s.rank()  # noqa: E731
    return {
        "months": len(h), "first": h.index.min(), "last": h.index.max(),
        "r_monthly": float(np.corrcoef(lh, lb)[0, 1]),
        "r_anomaly": float(np.corrcoef(ah, ab)[0, 1]),
        "r_yearly_rank": float(np.corrcoef(rank(yh), rank(yb))[0, 1]) if len(years) > 2 else float("nan"),
        "same_top3": set(yh.nlargest(3).index) == set(yb.nlargest(3).index),
        "top3_fire": sorted(int(y) for y in yh.nlargest(3).index),
        "top3_burned": sorted(int(y) for y in yb.nlargest(3).index),
        "yearly": pd.DataFrame({"fire_days": yh, "burned_km2": yb}),
    }


def seam_steps(series: pd.Series, gfed: pd.DataFrame, pre=(2006, 2011), mid=(2012, 2017), post=(2018, 2020)) -> dict:
    """Jump in the ratio fire days / GFED5 burned area where the satellites change.

    A record that only reflects satellite changes jumps at 2012 (VIIRS starts) relative to an
    independent record; a well-harmonized one does not. Returns the % step of the yearly
    ratio between the mean of `pre` and `mid` years (2012 seam) and `mid` and `post` (2018).
    """
    a = series.dropna()
    a = a.groupby(a.index.year).agg(["sum", "size"])
    a = a["sum"][a["size"] == 12]
    b = gfed["total"].groupby(gfed.index.year).sum()
    r = np.log(a / b).replace([np.inf, -np.inf], np.nan).dropna()
    m = lambda lo_hi: r[(r.index >= lo_hi[0]) & (r.index <= lo_hi[1])].mean()  # noqa: E731
    return {"step_2012": float(np.expm1(m(mid) - m(pre))), "step_2018": float(np.expm1(m(post) - m(mid)))}
