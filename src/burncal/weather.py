"""Weather inputs for the short-range forecast (burncal.forecast), from NASA POWER daily data.

For every forecast week ending on day t, only weather up to t is used (POWER is available up to
about 2 days before today, the same as the fire data):

    rain_7, rain_30     rain in the last 7 / 30 days (mm, log1p)
    rain_30_anom        log1p(rain_30) minus its usual value for this time of year (earlier years)
    dry_days            consecutive days with < 1 mm rain, ending on t
    tmax_7, rh_7, wind_7  mean daily maximum temperature, relative humidity, wind in the last 7 days
    soil, soil_anom     topsoil wetness (0-1) over the last 3 days, and its anomaly (earlier years)

States/provinces and Malaysian districts have their own point (fire-weighted centre, see
scripts/download_weather.py); a country uses the fire-weighted average of its states.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

WEATHER_FEATURES = ["rain_7", "rain_30", "rain_30_anom", "dry_days", "tmax_7", "rh_7", "wind_7", "soil", "soil_anom"]


def _dry_run(rain: np.ndarray, threshold: float = 1.0) -> np.ndarray:
    """Consecutive dry days ending on each day (NaN rain breaks nothing, counts as dry)."""
    out = np.zeros(len(rain))
    run = 0
    for i, r in enumerate(rain):
        run = run + 1 if not (r >= threshold) else 0
        out[i] = run
    return out


def _earlier_years_clim(dates: pd.Series, values: np.ndarray) -> np.ndarray:
    """Mean of `values` at the same time of year (+-3 days) in earlier years only."""
    doy = dates.dt.dayofyear.to_numpy()
    yr = dates.dt.year.to_numpy()
    diff = np.abs(((doy[None, :] - doy[:, None] + 182) % 365) - 182)
    close = (diff <= 3) & (yr[None, :] < yr[:, None]) & np.isfinite(values)[None, :]
    n = close.sum(axis=1)
    v = np.where(np.isfinite(values), values, 0.0)
    with np.errstate(invalid="ignore", divide="ignore"):
        return np.where(n > 0, (close @ v) / n, np.nan)


def point_weekly(daily: pd.DataFrame, week_ends: pd.DatetimeIndex) -> pd.DataFrame:
    """Weekly features of ONE point. daily: date, rain, tmax, rh, wind, soil (any order, gaps allowed)."""
    d = daily.set_index("date").sort_index()
    d = d[~d.index.duplicated()].asfreq("D")
    rain = d["rain"]
    feats = pd.DataFrame(index=d.index)
    feats["rain_7"] = np.log1p(rain.rolling(7, min_periods=5).sum())
    r30 = rain.rolling(30, min_periods=24).sum()
    feats["rain_30"] = np.log1p(r30)
    feats["dry_days"] = _dry_run(rain.to_numpy())
    feats["tmax_7"] = d["tmax"].rolling(7, min_periods=5).mean()
    feats["rh_7"] = d["rh"].rolling(7, min_periods=5).mean()
    feats["wind_7"] = d["wind"].rolling(7, min_periods=5).mean()
    feats["soil"] = d["soil"].rolling(3, min_periods=2).mean()
    w = feats.reindex(week_ends)
    dates = pd.Series(w.index)
    w["rain_30_anom"] = w["rain_30"].to_numpy() - _earlier_years_clim(dates, w["rain_30"].to_numpy())
    w["soil_anom"] = w["soil"].to_numpy() - _earlier_years_clim(dates, w["soil"].to_numpy())
    return w[WEATHER_FEATURES]


def area_weekly(daily: pd.DataFrame, points: pd.DataFrame, week_ends: pd.DatetimeIndex) -> pd.DataFrame:
    """Weekly weather per forecast area id ("adm1:IDN|Riau", "adm2:MYS|Sarawak|Miri", "country:IDN").

    daily: plat, plon, date + variables; points: country, adm1, adm2, plat, plon, weight."""
    per_point = {}
    for (lat, lon), g in daily.groupby(["plat", "plon"]):
        per_point[(round(lat, 2), round(lon, 2))] = point_weekly(g, week_ends)
    rows = []
    for _, p in points.iterrows():
        w = per_point.get((round(p["plat"], 2), round(p["plon"], 2)))
        if w is None:
            continue
        if isinstance(p["adm2"], str) and p["adm2"]:
            area = f"adm2:{p['country']}|{p['adm1']}|{p['adm2']}"
        else:
            area = f"adm1:{p['country']}|{p['adm1']}"
        rows.append(w.assign(area=area, week_end=w.index, _country=p["country"],
                             _weight=float(p["weight"]) if area.startswith("adm1") else np.nan))
    if not rows:
        return pd.DataFrame(columns=["area", "week_end", *WEATHER_FEATURES])
    t = pd.concat(rows, ignore_index=True)
    # countries: fire-weighted average of their states
    s = t[t["area"].str.startswith("adm1")]
    vals = s[WEATHER_FEATURES].to_numpy(float)
    wt = s["_weight"].to_numpy(float)[:, None] * np.isfinite(vals)
    num = pd.DataFrame(np.where(np.isfinite(vals), vals, 0.0) * wt, columns=WEATHER_FEATURES)
    den = pd.DataFrame(wt, columns=WEATHER_FEATURES)
    key = [s["_country"].to_numpy(), s["week_end"].to_numpy()]
    c = (num.groupby(key).sum() / den.groupby(key).sum().replace(0, np.nan)).reset_index()
    c.columns = ["_country", "week_end", *WEATHER_FEATURES]
    c["area"] = "country:" + c["_country"].astype(str)
    out = pd.concat([t.drop(columns=["_weight"]), c], ignore_index=True)
    return out[["area", "week_end", *WEATHER_FEATURES]]
