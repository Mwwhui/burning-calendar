"""Seasonal outlook (synthetic data only)."""

import numpy as np
import pandas as pd

from burncal.outlook import outlook, peak_season


def _series(link: float, seed=0):
    rng = np.random.default_rng(seed)
    idx = pd.period_range("2001-01", "2026-10", freq="M")
    oni = pd.Series(rng.normal(0, 1, len(idx)), idx).rolling(3, min_periods=1).mean()
    base = np.where(np.isin(idx.month, [12, 1, 2]), 100.0, 5.0)  # season Dec-Feb, wraps New Year
    h = pd.Series(base, idx)
    for y in range(2001, 2026):
        start = pd.Period(year=y, month=12, freq="M")
        factor = np.exp(link * oni[start - 2] + rng.normal(0, 0.15))
        for k in range(3):
            if start + k in h.index:
                h[start + k] *= factor
    return h, oni


def test_peak_season_wraps_new_year():
    h, _ = _series(0.0)
    months, share = peak_season(h)
    assert months == [12, 1, 2] and share > 0.8


def test_outlook_useful_when_linked():
    h, oni = _series(0.8)
    o = outlook(h, oni, pd.Timestamp("2026-11-05"))
    assert o["lead"] == 2 and o["season_start"] == pd.Period("2026-12", "M")
    assert o["skill"]["useful"] and o["skill"]["r"] > 0.8
    assert abs(o["p_below"] + o["p_normal"] + o["p_above"] - 1) < 1e-9
    assert 0.05 <= o["p_above"] <= 0.90
    big = oni.copy()
    big.iloc[-1] = 3.0  # far outside past values: chances still capped
    assert outlook(h, big, pd.Timestamp("2026-11-05"))["p_above"] == 0.90


def test_no_outlook_without_link():
    h, oni = _series(0.0, seed=3)
    o = outlook(h, oni, pd.Timestamp("2026-11-05"))
    assert not o["skill"]["useful"] and "p_above" not in o
