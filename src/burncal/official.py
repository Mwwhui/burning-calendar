"""Officially reported fire figures, to check the satellite record against ("detected and reported").

Only series that are published openly and year by year are included, each with its source.

Indonesia: yearly burned area ("indikasi luas kebakaran hutan dan lahan") from SiPongi, the
fire monitoring system of the Ministry of Environment and Forestry (KLHK, now Ministry of
Forestry). SiPongi maps burned area from Landsat/Sentinel images plus field checks, so it is
independent of the hotspot counts used here (it uses hotspots only to know where to look).

Malaysia: no open year-by-year official series was found. The Fire and Rescue Department
(JBPM/BOMBA) reports open-burning *cases* to the press with changing periods and categories,
which cannot be compared year to year (docs/decisions.md).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

SOURCES = {
    "sipongi": ("SiPongi (KLHK / Kementerian Kehutanan) via Mongabay Indonesia, 29 Apr 2025, "
                "'Karhutla satu dekade 7,7 juta hektar'"),
    "sipongi_2025": "SiPongi via VOI and Kompas (26 Mar 2026): 359,619.42 ha in 2025",
}

# hectares burned per year, Indonesia
INDONESIA_BURNED_HA = pd.Series({
    2015: 2_611_000, 2016: 438_363, 2017: 165_483, 2018: 529_266, 2019: 1_649_258, 2020: 296_942,
    2021: 358_867, 2022: 204_894, 2023: 1_161_000, 2024: 376_805, 2025: 359_619,
}, name="burned_ha", dtype=float)
INDONESIA_SOURCE = {y: "sipongi" for y in range(2015, 2025)} | {2025: "sipongi_2025"}


def spearman(a: pd.Series, b: pd.Series) -> float:
    a, b = a.align(b, join="inner")
    return float(np.corrcoef(a.rank(), b.rank())[0, 1]) if len(a) > 2 else float("nan")


def compare_with_official(annual_total: pd.Series, official: pd.Series = INDONESIA_BURNED_HA) -> dict:
    """Do the harmonized yearly totals rank the years like the official figures?

    Returns the years compared, the rank correlation, whether both put the same years in
    their top 3, and a table with each year's rank in both series.
    """
    a, o = annual_total.align(official, join="inner")
    t = pd.DataFrame({"fire_days": a, "official": o})
    t["rank_fire_days"] = t["fire_days"].rank(ascending=False).astype(int)
    t["rank_official"] = t["official"].rank(ascending=False).astype(int)
    top = lambda s: set(s.nlargest(3).index)  # noqa: E731
    return {"years": list(t.index), "spearman": spearman(a, o),
            "pearson_log": float(np.corrcoef(np.log(a), np.log(o))[0, 1]) if len(t) > 2 else float("nan"),
            "same_top3": top(a) == top(o), "table": t}
