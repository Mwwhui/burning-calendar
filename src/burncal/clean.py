"""Filter hotspots: bounding box, FIRMS type, detection confidence."""

from __future__ import annotations

import logging

import pandas as pd

from .config import Settings

log = logging.getLogger(__name__)


def clean(df: pd.DataFrame, settings: Settings | None = None) -> pd.DataFrame:
    """Return the hotspots that pass all filters.

    - bbox: keep points inside (west, south, east, north)
    - type: keep `settings.keep_type` (0 = presumed vegetation fire). Rows with no type
      (NRT files) are kept here; static sources are removed afterwards by the cell mask
      in `burncal.static` (applied in the cube build).
    - MODIS confidence >= modis_min_confidence; VIIRS confidence in viirs_keep_confidence
    """
    s = settings or Settings()
    n0 = len(df)
    out = df
    if s.bbox is not None:
        w, so, e, n = s.bbox
        out = out[out["longitude"].between(w, e) & out["latitude"].between(so, n)]
    out = out[out["type"].isna() | out["type"].isin(s.keep_type)]

    is_m = out["sensor"].eq("MODIS")
    is_v = out["sensor"].eq("VIIRS")
    m_ok = is_m & (pd.to_numeric(out["confidence"], errors="coerce") >= s.modis_min_confidence)
    v_ok = is_v & out["confidence"].astype(str).str.lower().isin(s.viirs_keep_confidence)
    out = out[m_ok | v_ok].copy()
    log.info("clean: kept %d of %d hotspots (%.0f%%)", len(out), n0, 100 * len(out) / max(n0, 1))
    return out
