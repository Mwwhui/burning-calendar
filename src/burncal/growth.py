"""Fire growth: from a fire's first 3 days, the chance it becomes big or long-lasting.

Events come from burncal.events (NOAA-20, touching ~1 km cells at most 5 days apart). The
model is issued at the end of an event's third day (days 0-2, burncal.events.EARLY_DAYS) and
uses only what is known then:

    the early_* columns (cells, cell-days, active days, fire radiative power, peat share,
    extent and area in days 0-2), where and when the fire started (latitude, longitude, day of
    year, country), the El Nino index with a 2-month publication lag, and how many other fires
    started in the same country in the 7 days before the issue date (a proxy for dry weather).

Targets: final area >= BIG_KM2 ("big") and lasting >= LONG_DAYS days ("long"). Events that are
already big by day 3 are left out of the "big" question (nothing to predict).

Evaluation: train on earlier years, test on each later year; compared with ranking fires by
their day-3 area alone (the obvious rule of thumb). Reported as ROC AUC, average precision
(area under the precision-recall curve) and how many of the eventual big fires are among the
top 1 % of scores.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .events import EARLY_DAYS

BIG_KM2 = 10.0
LONG_DAYS = 7
FEATURES = ["early_cells", "early_cell_days", "early_days", "log_early_frp_sum", "early_frp_max", "early_peat",
            "early_extent_km", "early_area_km2", "doy_sin", "doy_cos", "lat", "lon", "country_code", "oni",
            "log_recent_starts"]


def features(ev: pd.DataFrame, oni: pd.Series | None, countries: list[str] | None = None) -> pd.DataFrame:
    """Model inputs per event (known at the end of day EARLY_DAYS - 1) and both targets."""
    e = ev.copy()
    e["start"] = pd.to_datetime(e["start"])
    issue = e["start"] + pd.Timedelta(days=EARLY_DAYS - 1)
    doy = e["start"].dt.dayofyear
    f = pd.DataFrame(index=e.index)
    for c in ("early_cells", "early_cell_days", "early_days", "early_frp_max", "early_peat", "early_extent_km",
              "early_area_km2", "lat", "lon"):
        f[c] = e[c].astype(float)
    f["log_early_frp_sum"] = np.log1p(e["early_frp_sum"].astype(float))
    f["doy_sin"] = np.sin(2 * np.pi * doy / 365.25)
    f["doy_cos"] = np.cos(2 * np.pi * doy / 365.25)
    countries = countries or sorted(e["country"].dropna().astype(str).unique())
    f["country_code"] = e["country"].astype(str).map({c: i for i, c in enumerate(countries)}).astype(float)
    if oni is not None and len(oni):
        f["oni"] = (issue.dt.to_period("M") - 2).map(lambda p: oni.get(p, np.nan)).astype(float)
    else:
        f["oni"] = np.nan
    f["log_recent_starts"] = np.log1p(recent_starts(e))
    f["year"] = e["start"].dt.year
    f["big"] = (e["area_km2"] >= BIG_KM2).astype(int)
    f["long"] = (e["days"] >= LONG_DAYS).astype(int)
    f["already_big"] = e["early_area_km2"] >= BIG_KM2
    return f


def recent_starts(e: pd.DataFrame, window_days: int = 7) -> np.ndarray:
    """For each event: other events that started in the same country in the `window_days`
    days up to its issue date (start + EARLY_DAYS - 1). Uses only starts, known by then."""
    out = np.zeros(len(e))
    day = (pd.to_datetime(e["start"]) - pd.Timestamp("2000-01-01")).dt.days.to_numpy()
    country = e["country"].astype(str).to_numpy()
    for c in np.unique(country):
        idx = np.nonzero(country == c)[0]
        d = np.sort(day[idx])
        issue = day[idx] + EARLY_DAYS - 1
        hi = np.searchsorted(d, issue, side="right")
        lo = np.searchsorted(d, issue - window_days, side="right")
        out[idx] = hi - lo - 1  # minus itself
    return np.clip(out, 0, None)


def _fit(train: pd.DataFrame, target: str, seed: int = 0):
    from sklearn.ensemble import HistGradientBoostingClassifier

    m = HistGradientBoostingClassifier(max_iter=300, learning_rate=0.06, max_leaf_nodes=31, min_samples_leaf=50,
                                       categorical_features=[FEATURES.index("country_code")],
                                       class_weight=None, random_state=seed)
    m.fit(train[FEATURES].to_numpy(float), train[target].to_numpy(int))
    return m


def population(f: pd.DataFrame, target: str) -> pd.DataFrame:
    return f[~f["already_big"]] if target == "big" else f


def backtest(f: pd.DataFrame, test_years: list[int]) -> pd.DataFrame:
    """Scores for every test-year event from models trained on earlier years only."""
    rows = []
    for target in ("big", "long"):
        pop = population(f, target)
        for y in test_years:
            tr, te = pop[pop["year"] < y], pop[pop["year"] == y]
            if tr[target].sum() < 20 or te.empty:
                continue
            m = _fit(tr, target)
            rows.append(pd.DataFrame({"target": target, "year": y, "y": te[target].to_numpy(),
                                      "p": m.predict_proba(te[FEATURES].to_numpy(float))[:, 1],
                                      "baseline": te["early_area_km2"].to_numpy(float)
                                      + 1e-3 * te["early_cell_days"].to_numpy(float)}, index=te.index))
    return pd.concat(rows) if rows else pd.DataFrame()


def scores(bt: pd.DataFrame) -> pd.DataFrame:
    """ROC AUC, average precision and capture in the top 1 % for the model and the day-3-area rule."""
    from sklearn.metrics import average_precision_score, roc_auc_score

    out = []
    for target, g in bt.groupby("target"):
        if g["y"].nunique() < 2:
            continue
        r = {"target": target, "n": len(g), "positives": int(g["y"].sum()), "base_rate": float(g["y"].mean())}
        for name in ("p", "baseline"):
            k = max(1, int(len(g) * 0.01))
            top = g.nlargest(k, name)
            r[f"{name}_auc"] = float(roc_auc_score(g["y"], g[name]))
            r[f"{name}_ap"] = float(average_precision_score(g["y"], g[name]))
            r[f"{name}_top1pct_recall"] = float(top["y"].sum() / max(1, g["y"].sum()))
            r[f"{name}_top1pct_precision"] = float(top["y"].mean())
        out.append(r)
    return pd.DataFrame(out)


def fit_all(f: pd.DataFrame) -> dict:
    return {t: _fit(population(f, t), t) for t in ("big", "long")}


def predict(models: dict, f: pd.DataFrame) -> pd.DataFrame:
    X = f[FEATURES].to_numpy(float)
    out = pd.DataFrame(index=f.index)
    out["p_big"] = np.where(f["already_big"], 1.0, models["big"].predict_proba(X)[:, 1])
    out["p_long"] = models["long"].predict_proba(X)[:, 1]
    return out
