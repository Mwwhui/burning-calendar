"""End-to-end run: raw hotspots -> harmonized monthly series + reports."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

from .aggregate import monthly_counts, satellites_active
from .benchmark import seam_tests, source_switches
from .clean import clean
from .config import VIIRS_PLATFORMS, Settings
from .harmonize import HarmonizationResult, harmonize


@dataclass
class PipelineResult:
    hotspots: pd.DataFrame
    monthly: pd.DataFrame
    harmonization: HarmonizationResult
    seams: pd.DataFrame
    naive_seams: pd.DataFrame

    @property
    def table(self) -> pd.DataFrame:
        """Harmonized monthly table written to outputs/harmonized_monthly.csv."""
        t = self.harmonization.frame.copy()
        t["viirs_satellites_active"] = satellites_active(self.monthly, VIIRS_PLATFORMS)
        return t


def naive_series(monthly: pd.DataFrame) -> pd.Series:
    """The 'do nothing' record: MODIS (Terra+Aqua) before VIIRS exists, raw S-NPP/NOAA-20 after."""
    modis = monthly[[c for c in ("Terra", "Aqua") if c in monthly]].sum(axis=1, min_count=1)
    viirs = pd.Series(np.nan, index=monthly.index)
    for p in ("NOAA20", "SNPP"):
        if p in monthly:
            viirs = viirs.fillna(monthly[p])
    return viirs.fillna(modis)


def run(raw: pd.DataFrame, settings: Settings | None = None) -> PipelineResult:
    s = settings or Settings()
    hot = clean(raw, s)
    if s.country or s.adm1 or s.adm2:
        from .regions import assign_regions, filter_region
        if "country" not in hot:
            hot = assign_regions(hot, s.boundary_dir)
        hot = filter_region(hot, s.country, s.adm1, s.adm2)
        if hot.empty:
            raise ValueError(f"No hotspots left in region country={s.country} adm1={s.adm1} adm2={s.adm2}")
    monthly = monthly_counts(hot, unit=s.unit, grid_deg=s.grid_deg)
    return run_monthly(monthly, s, hotspots=hot)


def run_monthly(monthly: pd.DataFrame, settings: Settings | None = None,
                hotspots: pd.DataFrame | None = None) -> PipelineResult:
    """Harmonize + seam tests on an already aggregated monthly table (e.g. from the cube)."""
    s = settings or Settings()
    result = harmonize(monthly, s)
    seams = seam_tests(result.series, source_switches(result.frame["source"]))
    naive = naive_series(monthly)
    naive_switches = [p for p in ("2012-01",) if pd.Period(p, "M") in naive.index]
    hot = hotspots if hotspots is not None else pd.DataFrame()
    return PipelineResult(hot, monthly, result, seams, seam_tests(naive, naive_switches))


def run_cube(cube: pd.DataFrame, settings: Settings | None = None) -> PipelineResult:
    """Harmonize one region from the monthly cube (settings.country/adm1/adm2; country None = all Asia, or a list)."""
    from .cube import monthly_from_cube

    s = settings or Settings()
    monthly = monthly_from_cube(cube, s.country, s.adm1, s.adm2, unit=s.unit)
    return run_monthly(monthly, s)


def write_outputs(res: PipelineResult, out_dir: str | Path, write_hotspots: bool = False) -> list[Path]:
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    written = []

    def save(df: pd.DataFrame, name: str, **kw):
        p = out / name
        df.to_csv(p, **kw)
        written.append(p)

    save(res.table, "harmonized_monthly.csv", index_label="month")
    save(res.monthly, "monthly_by_platform.csv", index_label="month")
    save(res.harmonization.annual(), "harmonized_annual.csv")
    save(res.seams, "seam_tests.csv", index=False)
    for step in res.harmonization.steps:
        if step.loyo is not None:
            save(step.loyo, f"benchmark_loyo_{step.donor}.csv", index_label="method")
        if step.holdout is not None and not step.holdout.empty:
            save(step.holdout, f"benchmark_holdout_{step.donor}.csv", index_label="method")
    report = {
        "steps": [st.to_dict() for st in res.harmonization.steps],
        "seams": res.seams.to_dict(orient="records"),
        "naive_seams": res.naive_seams.to_dict(orient="records"),
    }
    p = out / "harmonization_report.json"
    p.write_text(json.dumps(report, indent=2, default=str), encoding="utf-8")
    written.append(p)
    if write_hotspots:
        save(res.hotspots, "clean_hotspots.csv", index=False)
    return written
