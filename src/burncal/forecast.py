"""Short-range fire forecast per area: next 7 days and the 3 weeks after.

Unit and data
    Weekly VIIRS fire days (cell-days on local solar dates) from the daily tables: Suomi NPP
    before 1 Apr 2018, NOAA-20 from then on. The two carry the same instrument (S-NPP sees
    99.7 % of NOAA-20, docs/decisions.md), so 2012-2026 is one consistent sensor family and no
    conversion is needed. Weeks end on the last complete day, so the latest week is whole.

Model
    One pooled model for all areas (small districts borrow strength from big ones):
    scikit-learn HistGradientBoostingRegressor with quantile loss (10th, 50th, 90th
    percentile) on log1p fire days. Features known at the issue date only: the last 1-4
    weeks, the last 8 weeks, the usual amount for the target weeks and the current week
    (mean of earlier years only), this week's anomaly, time of year, the El Nino index
    available then (ONI, 2-month publication lag) and the area's peat share and size.

Honesty
    Rolling-origin backtest: for every test year, the model is trained only on weeks that
    ended at least 4 weeks before the year starts. It is compared with two simple forecasts:
    persistence (the last week / the last 4 weeks) and climatology (the usual amount for
    those dates). An area gets a forecast in the app only when the model beat both in the
    backtest (skill > SKILL_MIN on mean absolute log error).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

QUANTILES = (0.1, 0.5, 0.9)
HORIZONS = {"h1": (1, 1), "h4": (2, 4)}  # target weeks after the issue week (inclusive)
SKILL_MIN = 0.05
FIRST_YEAR = 2012
NOAA20_FROM = pd.Timestamp("2018-04-01")

FEATURES = ["lag1", "lag2", "lag3", "lag4", "sum4", "sum8", "clim_now", "anom_now", "clim_h1", "clim_h4",
            "doy_sin", "doy_cos", "oni", "peat_share", "log_size", "country_code"]


def viirs_daily(admin: pd.DataFrame, keys: list[str]) -> pd.DataFrame:
    """date x area daily VIIRS cell-days (S-NPP before NOAA20_FROM, NOAA-20 after).
    `keys`: region columns that define an area, e.g. ["country"] or ["country", "adm1"]."""
    a = admin[admin["date"] >= pd.Timestamp(FIRST_YEAR, 1, 1)]
    sat = a["satellite"].astype(str)
    use = ((sat == "SNPP") & (a["date"] < NOAA20_FROM)) | ((sat == "NOAA20") & (a["date"] >= NOAA20_FROM))
    a = a[use]
    for k in keys:
        a = a[a[k].notna() & (a[k].astype(str) != "")]
    return a.groupby(["date", *keys], observed=True)["cell_days"].sum().reset_index()


def weekly(daily: pd.DataFrame, keys: list[str], last_day: pd.Timestamp) -> pd.DataFrame:
    """Weekly sums per area; week w ends on last_day - 7 * w (w = 0 is the latest full week).
    Returns columns: *keys, week_end, y (fire days), with zero weeks filled in."""
    last_day = pd.Timestamp(last_day).normalize()
    d = daily[daily["date"] <= last_day].copy()
    d["w"] = ((last_day - d["date"]).dt.days // 7).astype(int)
    w = d.groupby([*keys, "w"], observed=True)["cell_days"].sum().reset_index()
    n_weeks = int(w["w"].max()) + 1 if len(w) else 0
    areas = w[keys].drop_duplicates()
    full = areas.merge(pd.DataFrame({"w": np.arange(n_weeks)}), how="cross")
    full = full.merge(w, on=[*keys, "w"], how="left").fillna({"cell_days": 0})
    full["week_end"] = last_day - pd.to_timedelta(full["w"] * 7, unit="D")
    return full.rename(columns={"cell_days": "y"}).drop(columns="w").sort_values([*keys, "week_end"])


def _clim(g: pd.DataFrame) -> pd.Series:
    """Usual log1p fire days for each week's calendar position, from earlier years only.
    Matches weeks by day of year (+-3 days) and averages all previous years."""
    doy = g["week_end"].dt.dayofyear.to_numpy()
    yr = g["week_end"].dt.year.to_numpy()
    ly = np.log1p(g["y"].to_numpy(float))
    diff = np.abs(((doy[None, :] - doy[:, None] + 182) % 365) - 182)
    close = (diff <= 3) & (yr[None, :] < yr[:, None])  # row i: weeks of earlier years near i's date
    n = close.sum(axis=1)
    with np.errstate(invalid="ignore", divide="ignore"):
        out = np.where(n > 0, (close @ ly) / n, np.nan)
    return pd.Series(out, index=g.index)


def features(wk: pd.DataFrame, keys: list[str], oni: pd.Series | None, peat_share: pd.Series | None,
             size: pd.Series | None, countries: list[str]) -> pd.DataFrame:
    """Feature rows for every (area, issue week). Targets y_h1 / y_h4 are log1p of the next
    week / weeks 2-4 (NaN at the end of the record)."""
    parts = []
    for key, g in wk.groupby(keys, observed=True, sort=False):
        g = g.sort_values("week_end").reset_index(drop=True)
        ly = np.log1p(g["y"].astype(float))
        f = pd.DataFrame({"week_end": g["week_end"]})
        for k in keys:
            f[k] = g[k]
        for lag in range(1, 5):
            f[f"lag{lag}"] = ly.shift(lag - 1)  # lag1 = the week that just ended
        f["sum4"] = np.log1p(g["y"].rolling(4).sum())
        f["sum8"] = np.log1p(g["y"].rolling(8).sum())
        clim = _clim(g)
        f["clim_now"] = clim
        f["anom_now"] = f["lag1"] - clim
        f["clim_h1"] = clim.shift(-1)
        f["clim_h4"] = np.log1p(np.expm1(clim).shift(-2) + np.expm1(clim).shift(-3) + np.expm1(clim).shift(-4))
        # targets
        f["y_h1"] = ly.shift(-1)
        f["y_h4"] = np.log1p(g["y"].shift(-2) + g["y"].shift(-3) + g["y"].shift(-4))
        f["actual_h1"] = g["y"].shift(-1)
        f["actual_h4"] = g["y"].shift(-2) + g["y"].shift(-3) + g["y"].shift(-4)
        parts.append(f)
    out = pd.concat(parts, ignore_index=True)
    # the target weeks' calendar position (known in advance) for clim_h1/h4 at the end of the record
    doy = (out["week_end"] + pd.Timedelta(days=7)).dt.dayofyear
    out["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    out["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    if oni is not None and len(oni):
        avail = (out["week_end"].dt.to_period("M") - 2)
        out["oni"] = avail.map(lambda p: oni.get(p, np.nan)).astype(float)
    else:
        out["oni"] = np.nan
    area_key = out[keys].astype(str).agg("|".join, axis=1)
    out["area"] = area_key
    out["peat_share"] = area_key.map(peat_share).astype(float) if peat_share is not None else np.nan
    out["log_size"] = np.log1p(area_key.map(size).astype(float)) if size is not None else np.nan
    out["country_code"] = out["country"].astype(str).map({c: i for i, c in enumerate(countries)}).astype(float)
    return out


def _fill_clim(f: pd.DataFrame) -> pd.DataFrame:
    """At the very end of the record the next weeks' climatology is not in the table yet:
    approximate it with the current week's (one week apart)."""
    f = f.copy()
    f["clim_h1"] = f["clim_h1"].fillna(f["clim_now"])
    f["clim_h4"] = f["clim_h4"].fillna(np.log1p(3 * np.expm1(f["clim_now"])))
    return f


def feature_names(f: pd.DataFrame) -> list[str]:
    """Base features plus the weather inputs present in `f` (burncal.weather)."""
    from .weather import WEATHER_FEATURES
    return FEATURES + [c for c in WEATHER_FEATURES if c in f.columns and f[c].notna().any()]


@dataclass
class Fitted:
    models: dict  # (horizon, quantile) -> estimator
    names: list | None = None  # feature columns used


def fit(train: pd.DataFrame, seed: int = 0) -> Fitted:
    from sklearn.ensemble import HistGradientBoostingRegressor

    models = {}
    names = feature_names(train)
    for h in HORIZONS:
        t = train.dropna(subset=[f"y_{h}", "lag1", "clim_now"])
        X = t[names].to_numpy(float)
        cat = [names.index("country_code")]
        for q in QUANTILES:
            # no l2 penalty: with quantile loss (constant hessians) it shrinks every update and the
            # model underfits badly (Malaysia backtest MAE 0.30 -> 0.21 without it)
            m = HistGradientBoostingRegressor(loss="quantile", quantile=q, max_iter=400, learning_rate=0.08,
                                              max_leaf_nodes=31, min_samples_leaf=40,
                                              categorical_features=cat, random_state=seed)
            m.fit(X, t[f"y_{h}"].to_numpy(float))
            models[(h, q)] = m
    return Fitted(models, names)


def predict(m: Fitted, f: pd.DataFrame) -> pd.DataFrame:
    """Quantiles of fire days (not log) per row and horizon; sorted so q10 <= q50 <= q90."""
    X = _fill_clim(f)[m.names or FEATURES].to_numpy(float)
    out = pd.DataFrame(index=f.index)
    for h in HORIZONS:
        qs = np.column_stack([np.expm1(m.models[(h, q)].predict(X)) for q in QUANTILES])
        qs = np.sort(np.clip(qs, 0, None), axis=1)
        for j, q in enumerate(QUANTILES):
            out[f"{h}_q{int(q * 100)}"] = qs[:, j]
    return out


def baselines(f: pd.DataFrame) -> pd.DataFrame:
    """Persistence and climatology forecasts (fire days) for both horizons."""
    f = _fill_clim(f)
    last = np.expm1(f["lag1"])
    last4 = np.expm1(f["sum4"]) / 4
    return pd.DataFrame({
        "h1_persist": last, "h4_persist": 3 * last4,
        "h1_clim": np.expm1(f["clim_h1"]), "h4_clim": np.expm1(f["clim_h4"]),
    }, index=f.index)


def backtest(f: pd.DataFrame, test_years: list[int], gap_weeks: int = 4) -> pd.DataFrame:
    """Rolling-origin backtest. For each year, train on issue weeks ending >= gap_weeks + 4
    weeks before 1 January (so no training target overlaps the test year), predict that year."""
    rows = []
    for y in test_years:
        start = pd.Timestamp(y, 1, 1)
        train = f[f["week_end"] < start - pd.Timedelta(weeks=gap_weeks + 4)]
        test = f[(f["week_end"] >= start) & (f["week_end"] < pd.Timestamp(y + 1, 1, 1))]
        test = test.dropna(subset=["lag1", "clim_now", "clim_h1", "clim_h4"])
        if train.empty or test.empty:
            continue
        m = fit(train)
        p = predict(m, test).join(baselines(test))
        p["area"] = test["area"].to_numpy()
        p["week_end"] = test["week_end"].to_numpy()
        p["actual_h1"] = test["actual_h1"].to_numpy()
        p["actual_h4"] = test["actual_h4"].to_numpy()
        p["test_year"] = y
        rows.append(p)
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


def skill(bt: pd.DataFrame, by: str | None = "area") -> pd.DataFrame:
    """Mean absolute log error of the model and both baselines, skill vs each, interval
    coverage (10-90 %) and hit rate of 'above usual', per area (or overall with by=None)."""
    out = []
    groups = [("all", bt)] if by is None else bt.groupby(by)
    for key, g in groups:
        r = {"area": key}
        for h in HORIZONS:
            a = g[f"actual_{h}"]
            ok = a.notna()
            if ok.sum() < 10:
                continue
            la = np.log1p(a[ok])
            mae = lambda x: float(np.mean(np.abs(np.log1p(g.loc[ok, x]) - la)))  # noqa: E731
            m, p, c = mae(f"{h}_q50"), mae(f"{h}_persist"), mae(f"{h}_clim")
            r[f"{h}_n"] = int(ok.sum())
            r[f"{h}_mae"] = m
            r[f"{h}_skill_persist"] = 1 - m / p if p > 0 else np.nan
            r[f"{h}_skill_clim"] = 1 - m / c if c > 0 else np.nan
            r[f"{h}_coverage"] = float(((a[ok] >= g.loc[ok, f"{h}_q10"]) & (a[ok] <= g.loc[ok, f"{h}_q90"])).mean())
            above_pred = g.loc[ok, f"{h}_q50"] > g.loc[ok, f"{h}_clim"]
            above_true = a[ok] > g.loc[ok, f"{h}_clim"]
            r[f"{h}_hit"] = float((above_pred == above_true).mean())
        out.append(r)
    return pd.DataFrame(out)


def p_above(q10: float, q50: float, q90: float, usual: float) -> float:
    """Chance the outcome is above `usual`, from three quantiles (piecewise linear CDF,
    clipped to 5-95 % like the seasonal outlook)."""
    xs, ps = [q10, q50, q90], [0.1, 0.5, 0.9]
    if usual <= xs[0]:
        p = 0.1 * usual / xs[0] if xs[0] > 0 else 0.0
    elif usual >= xs[2]:
        p = 0.95
    else:
        p = float(np.interp(usual, xs, ps))
    return float(np.clip(1 - p, 0.05, 0.95))
