"""Settings and constants.

Satellite facts that drive the defaults (see docs/decisions.md):
- Suomi NPP stopped delivering data on 2 Nov 2026 and was decommissioned, so it
  cannot be the reference series. NOAA-20 (2018-) is the reference.
- Aqua MODIS drifted from a 13:30 to a ~15:50 afternoon overpass before its planned
  Aug 2026 shutdown; Terra drifted earlier in the morning. MODIS is therefore only
  calibrated on windows before the drift became large.
- Before July 2002 only Terra flew, so Terra-only months need their own step
  (the "2002 seam").
"""

from __future__ import annotations

from dataclasses import dataclass, field

PLATFORMS: tuple[str, ...] = ("Terra", "Aqua", "SNPP", "NOAA20", "NOAA21")
SENSOR_OF: dict[str, str] = {
    "Terra": "MODIS",
    "Aqua": "MODIS",
    "SNPP": "VIIRS",
    "NOAA20": "VIIRS",
    "NOAA21": "VIIRS",
}
VIIRS_PLATFORMS: tuple[str, ...] = tuple(p for p in PLATFORMS if SENSOR_OF[p] == "VIIRS")

# Malaysia (Peninsular + Sabah/Sarawak), west, south, east, north
MALAYSIA_BBOX: tuple[float, float, float, float] = (99.5, 0.8, 119.5, 7.5)


@dataclass(frozen=True)
class FillStep:
    """One link of the harmonization chain.

    Months where the current series is missing and `donor` has data are filled with
    `donor` converted to reference-equivalent counts. The conversion is fitted on the
    months inside [fit_start, fit_end] where both are present.
    method: "best" (1-SE rule on leave-one-year-out RMSE(log), M0 excluded) or M0-M4;
    for a multi-donor step either one method for all routes or one per donor ("M3+M2").

    `donor` may join several platforms with "+" (e.g. "Aqua+Terra"): each is converted
    on its own (own method choice) and the conversions are averaged in log space, only
    in months where all of them have data. The band then also covers every single route.
    """

    donor: str
    fit_start: str | None = None  # "YYYY-MM", inclusive
    fit_end: str | None = None
    method: str = "best"
    note: str = ""


DEFAULT_FILL_STEPS: tuple[FillStep, ...] = (
    FillStep("SNPP", "2018-04", "2026-10", note="VIIRS 2012-2018 before NOAA-20; same instrument design"),
    FillStep("NOAA21", "2024-01", None, note="gap filling during NOAA-20 outages"),
    FillStep("Aqua+Terra", "2012-01", "2020-12", method="M3+M2",
             note="MODIS 2002-2011, log-mean of Aqua (M3) and Terra (M2) routes. Backcast fit 2017-20 -> "
                  "predict S-NPP 2012-15, 9 regions: monthly RMSE(log) 0.233 vs 0.274 for Aqua alone; annual "
                  "bias +4% vs +10% (SEA). Window ends before orbit drift"),
    FillStep("Aqua", "2012-01", "2020-12", note="Aqua months without Terra data"),
    FillStep("Terra", "2002-07", "2005-06", note="Terra-only months before Aqua (2002 seam)"),
)


@dataclass
class Settings:
    # Region filter (west, south, east, north); None keeps everything in the files
    bbox: tuple[float, float, float, float] | None = None
    # Boundary filter (needs data/external from scripts/download_context.py):
    # country ISO3 ("MYS", "IDN", "BRN", "THA", "PHL", "Other"), state/province, district
    country: str | None = None
    adm1: tuple[str, ...] | str | None = None
    adm2: tuple[str, ...] | str | None = None
    boundary_dir: str | None = None
    # Cleaning
    modis_min_confidence: int = 30
    viirs_keep_confidence: tuple[str, ...] = ("n", "h", "nominal", "high")
    keep_type: tuple[int, ...] = (0,)
    # Static heat sources (gas flares, industry, volcanoes): Parquet mask of ~1 km cells
    # built by scripts/build_static_mask.py; hotspots inside are dropped for every
    # satellite and year (see burncal.static). None = no mask.
    static_mask: str | None = None
    # Counting unit: "cell_days" (each grid cell once per local solar day) or "points"
    unit: str = "cell_days"
    grid_deg: float = 0.01
    # Harmonization
    reference: str = "NOAA20"
    fill_steps: tuple[FillStep, ...] = DEFAULT_FILL_STEPS
    holdout_years: tuple[int, ...] = (2015, 2019, 2022)
    interval: float = 0.90  # width of the uncertainty band on converted months
    # Method choice per step: "1se" = simplest method within one paired standard error
    # of the best (needs >= min_years_for_se held-out years; with fewer, a more complex
    # method must beat the simpler one in every year); "min" = lowest mean error.
    selection_rule: str = "1se"
    min_years_for_se: int = 5
    min_pairs: int = 24  # minimum overlapping months to fit a step
    # Minimum months in the fit window where both donor and reference saw fires. Below this
    # the area has too few fires to learn a conversion (Malaysian state test: areas with 0-1
    # such months got 0-56 % yearly coverage, all states with >= 23 got 89-100 %), so the
    # months are left empty instead of filled with a guess.
    min_fire_pairs: int = 12
    # Calendar
    baseline_years: tuple[int, int] = (2003, 2022)
    extra: dict = field(default_factory=dict)
