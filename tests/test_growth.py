"""burncal.growth: features known at day 3 only, targets, and a backtest on synthetic fires."""

import numpy as np
import pandas as pd

from burncal.growth import BIG_KM2, FEATURES, backtest, features, recent_starts, scores


def _events(n=4000, seed=0):
    """Synthetic fires: those with strong early fire power on peat tend to grow and last."""
    rng = np.random.default_rng(seed)
    start = pd.Timestamp("2019-01-01") + pd.to_timedelta(rng.integers(0, 365 * 4, n), unit="D")
    frp = rng.lognormal(2, 1, n)
    peat = rng.random(n) < 0.3
    grow = rng.random(n) < 1 / (1 + np.exp(-(np.log(frp) - 3.5 + 1.5 * peat)))
    early_area = rng.uniform(1.2, 4, n)
    area = np.where(grow, early_area * rng.uniform(3, 10, n), early_area * rng.uniform(1, 1.5, n))
    days = np.where(grow, rng.integers(7, 30, n), rng.integers(1, 6, n))
    return pd.DataFrame({
        "event_id": np.arange(n), "start": start, "end": start + pd.to_timedelta(days - 1, unit="D"), "days": days,
        "area_km2": area, "country": rng.choice(["MYS", "IDN"], n), "lat": rng.uniform(0, 5, n),
        "lon": rng.uniform(100, 118, n), "early_cells": np.round(early_area / 1.2), "early_cell_days": 3,
        "early_days": 2, "early_frp_sum": frp * 2, "early_frp_max": frp, "early_peat": peat.astype(float),
        "early_extent_km": 2.0, "early_area_km2": early_area,
    })


def test_features_and_targets():
    ev = _events(200)
    f = features(ev, None)
    assert set(FEATURES) <= set(f.columns)
    assert (f["big"] == (ev["area_km2"] >= BIG_KM2)).all()
    assert (f["long"] == (ev["days"] >= 7)).all()


def test_recent_starts_counts_only_earlier_starts_in_the_same_country():
    ev = pd.DataFrame({"start": pd.to_datetime(["2020-01-01", "2020-01-02", "2020-01-20", "2020-01-02"]),
                       "country": ["MYS", "MYS", "MYS", "IDN"]})
    # issue = start + 2 days; window 7 days back from the issue date
    assert recent_starts(ev).tolist() == [1, 1, 0, 0]


def test_backtest_learns_the_signal():
    f = features(_events(), None)
    bt = backtest(f, [2022])
    sc = scores(bt).set_index("target")
    assert sc.loc["long", "p_auc"] > 0.75
    assert sc.loc["long", "p_auc"] > sc.loc["long", "baseline_auc"]
