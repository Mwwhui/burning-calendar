"""burncal.weather: weekly weather inputs use only weather up to the forecast day."""

import numpy as np
import pandas as pd

from burncal.weather import WEATHER_FEATURES, area_weekly, point_weekly


def _daily(lat=1.25, lon=110.25, days=pd.date_range("2014-01-01", "2016-12-31"), rain_fn=None):
    rng = np.random.default_rng(0)
    rain = rain_fn(days) if rain_fn else rng.gamma(0.5, 10, len(days))
    return pd.DataFrame({"date": days, "rain": rain, "tmax": 31.0, "rh": 80.0, "wind": 1.0, "soil": 0.5,
                         "plat": lat, "plon": lon})


def test_rain_windows_and_dry_spell():
    days = pd.date_range("2015-01-01", "2015-03-31")
    rain = np.where(days < pd.Timestamp("2015-03-20"), 5.0, 0.0)  # dry from 20 March
    w = point_weekly(_daily(days=days, rain_fn=lambda d: rain), pd.DatetimeIndex(["2015-03-25", "2015-03-31"]))
    assert w.loc["2015-03-25", "dry_days"] == 6
    assert w.loc["2015-03-31", "dry_days"] == 12
    assert w.loc["2015-03-31", "rain_7"] == 0.0
    assert np.isclose(w.loc["2015-03-25", "rain_30"], np.log1p(5 * 24))


def test_no_look_ahead_rain_after_the_week_is_ignored():
    days = pd.date_range("2015-01-01", "2015-03-31")
    a = point_weekly(_daily(days=days, rain_fn=lambda d: np.full(len(d), 2.0)), pd.DatetimeIndex(["2015-03-10"]))
    wet_later = np.where(days > pd.Timestamp("2015-03-10"), 99.0, 2.0)
    b = point_weekly(_daily(days=days, rain_fn=lambda d: wet_later), pd.DatetimeIndex(["2015-03-10"]))
    pd.testing.assert_frame_equal(a, b)


def test_anomaly_uses_earlier_years_only_and_country_average():
    week_ends = pd.date_range("2014-01-07", "2016-12-27", freq="7D")
    d1 = _daily(1.25, 110.25)
    d2 = _daily(2.25, 112.25).assign(tmax=35.0)
    pts = pd.DataFrame({"country": ["MYS", "MYS"], "adm1": ["A", "B"], "adm2": [None, None],
                        "plat": [1.25, 2.25], "plon": [110.25, 112.25], "weight": [3.0, 1.0]})
    t = area_weekly(pd.concat([d1, d2]), pts, week_ends)
    assert set(WEATHER_FEATURES) <= set(t.columns)
    a = t[t["area"] == "adm1:MYS|A"]
    assert a.loc[a["week_end"].dt.year == 2014, "rain_30_anom"].isna().all()  # no earlier year
    c = t[t["area"] == "country:MYS"]
    assert np.allclose(c["tmax_7"].dropna(), 0.75 * 31 + 0.25 * 35)  # fire-weighted
