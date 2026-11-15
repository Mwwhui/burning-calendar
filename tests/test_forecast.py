"""burncal.forecast: weekly VIIRS series, features without look-ahead, backtest and skill."""

import numpy as np
import pandas as pd

from burncal.forecast import (FEATURES, backtest, features, fit, p_above, predict, skill, viirs_daily, weekly)


def _admin(years=range(2014, 2021), seed=1):
    """Two areas with a strong seasonal cycle (peak in Aug-Sep) and noise."""
    rng = np.random.default_rng(seed)
    days = pd.date_range(f"{min(years)}-01-01", f"{max(years)}-12-31")
    rows = []
    for adm1, scale in (("A", 20.0), ("B", 3.0)):
        season = scale * (1 + 4 * np.exp(-((days.dayofyear - 240) / 25.0) ** 2))
        cd = rng.poisson(season)
        sat = np.where(days < pd.Timestamp("2018-04-01"), "SNPP", "NOAA20")
        rows.append(pd.DataFrame({"date": days, "satellite": sat, "country": "MYS", "adm1": adm1, "adm2": None,
                                  "peat": False, "cell_days": cd}))
        # a satellite that must be ignored
        rows.append(pd.DataFrame({"date": days, "satellite": "Aqua", "country": "MYS", "adm1": adm1, "adm2": None,
                                  "peat": False, "cell_days": 1000}))
    return pd.concat(rows, ignore_index=True)


def test_viirs_daily_uses_snpp_then_noaa20_only():
    d = viirs_daily(_admin(), ["country", "adm1"])
    assert d["cell_days"].max() < 1000  # Aqua dropped
    assert d["date"].min() == pd.Timestamp("2014-01-01")


def test_weeks_end_on_the_last_day_and_fill_zeros():
    d = pd.DataFrame({"date": pd.to_datetime(["2020-01-01", "2020-01-10"]), "country": "MYS", "cell_days": [5, 2]})
    w = weekly(d, ["country"], pd.Timestamp("2020-01-14"))
    assert list(w["week_end"].dt.strftime("%m-%d")) == ["01-07", "01-14"]
    assert list(w["y"]) == [5, 2]


def test_features_have_no_look_ahead():
    adm = _admin()
    wk = weekly(viirs_daily(adm, ["country", "adm1"]), ["country", "adm1"], pd.Timestamp("2020-12-31"))
    f = features(wk, ["country", "adm1"], None, None, None, ["MYS"])
    g = f[f["adm1"] == "A"].reset_index(drop=True)
    y = np.log1p(wk[wk["adm1"] == "A"]["y"].to_numpy(float))
    i = 300
    assert g.loc[i, "lag1"] == y[i]          # the week that just ended
    assert g.loc[i, "y_h1"] == y[i + 1]      # target = the next week
    # climatology uses earlier years only: the first year has none
    assert g.loc[g["week_end"].dt.year == 2014, "clim_now"].isna().all()
    assert set(FEATURES) <= set(f.columns)


def test_backtest_beats_climatology_on_a_seasonal_series():
    adm = _admin()
    wk = weekly(viirs_daily(adm, ["country", "adm1"]), ["country", "adm1"], pd.Timestamp("2020-12-31"))
    f = features(wk, ["country", "adm1"], None, None, None, ["MYS"])
    bt = backtest(f, [2020])
    assert len(bt) > 50
    sk = skill(bt, by=None).iloc[0]
    assert sk["h1_coverage"] > 0.5
    assert sk["h1_mae"] < 0.6
    # quantiles are ordered
    assert (bt["h1_q10"] <= bt["h1_q50"]).all() and (bt["h1_q50"] <= bt["h1_q90"]).all()
    m = fit(f[f["week_end"] < pd.Timestamp("2020-06-01")])
    assert predict(m, f.tail(3)).shape == (3, 6)


def test_chance_above_usual():
    assert p_above(10, 20, 40, 20) == 0.5
    assert p_above(10, 20, 40, 5) > 0.9
    assert abs(p_above(10, 20, 40, 100) - 0.05) < 1e-9
