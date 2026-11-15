"""Scoring harmonization methods and testing for seams.

- evaluate / holdout_benchmark / loyo_benchmark: compare M0-M4 on hidden years
- overlap_drift: does the donor/reference relationship change over the years?
  (catches MODIS orbit drift, which a single fit would silently absorb)
- step_at / seam_tests: deseasonalized level change at each source switch, ranked
  against "placebo" switches at dates where nothing changed
- pettitt: Pettitt change-point test
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from .harmonize import METHODS


def evaluate(pred, obs) -> dict:
    pred, obs = np.asarray(pred, float), np.asarray(obs, float)
    lp, lo = np.log1p(pred), np.log1p(obs)
    corr = np.corrcoef(pred, obs)[0, 1] if len(obs) > 1 and np.std(pred) > 0 and np.std(obs) > 0 else np.nan
    return {
        "MAE": float(np.mean(np.abs(pred - obs))),
        "RMSE_log": float(np.sqrt(np.mean((lp - lo) ** 2))),
        "bias_pct": float(100 * (pred.sum() - obs.sum()) / obs.sum()) if obs.sum() > 0 else np.nan,
        "corr": float(corr),
        "n": int(len(obs)),
    }


def holdout_benchmark(pairs: pd.DataFrame, holdout_years, methods=None) -> pd.DataFrame:
    """Fit on all years except `holdout_years`, score on them. Empty if none are in `pairs`."""
    methods = methods or METHODS
    hold = [y for y in holdout_years if y in set(pairs["year"])]
    train, test = pairs[~pairs["year"].isin(hold)], pairs[pairs["year"].isin(hold)]
    if not hold or len(train) < 3:
        return pd.DataFrame()
    rows = {}
    for name, fit in methods.items():
        pred = fit(train)(test["x"].to_numpy(float), test["mon"].to_numpy())
        rows[name] = evaluate(pred, test["y"])
    out = pd.DataFrame(rows).T.sort_values("RMSE_log")
    out.attrs["holdout_years"] = hold
    return out


def loyo_benchmark(pairs: pd.DataFrame, methods=None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Leave-one-year-out. Returns (summary per method, out-of-sample predictions)."""
    methods = methods or METHODS
    scores, preds = [], []
    for y in sorted(pairs["year"].unique()):
        tr, te = pairs[pairs["year"] != y], pairs[pairs["year"] == y]
        if len(tr) < 3:
            continue
        for name, fit in methods.items():
            p = fit(tr)(te["x"].to_numpy(float), te["mon"].to_numpy())
            scores.append({"method": name, "year": y, **evaluate(p, te["y"])})
            preds.append(pd.DataFrame({"method": name, "year": y, "pred": p, "obs": te["y"].to_numpy(float)},
                                      index=te.index))
    scores = pd.DataFrame(scores)
    summary = scores.groupby("method").agg(
        RMSE_log_mean=("RMSE_log", "mean"), RMSE_log_std=("RMSE_log", "std"),
        bias_pct_mean=("bias_pct", "mean"), years=("year", "nunique"),
    ).sort_values("RMSE_log_mean")
    return summary, pd.concat(preds)


def per_year_rmse(preds: pd.DataFrame) -> pd.DataFrame:
    """Leave-one-year-out predictions -> table of RMSE(log1p) with rows = year, columns = method."""
    err = (np.log1p(preds["pred"].astype(float)) - np.log1p(preds["obs"].astype(float))) ** 2
    return np.sqrt(err.groupby([preds["year"], preds["method"]]).mean()).unstack("method")


def select_method(per_year: pd.DataFrame, rule: str = "1se", min_years_for_se: int = 5,
                  order=None) -> tuple[str, str]:
    """Choose a harmonization method from per-year LOYO errors. Returns (method, reason).

    rule="min": lowest mean RMSE(log1p).
    rule="1se": prefer simpler methods (order = simplest first) unless a more complex one
    is clearly better:
      - with >= min_years_for_se years: the paired one-standard-error rule. For each
        method, the per-year differences to the best method are averaged; the simplest
        method whose mean difference is <= one standard error of those differences is
        chosen. Pairing by year removes the shared difficulty of each year (2015 is hard
        for every method), which an unpaired SE would count as noise.
      - with fewer years the SE is unreliable (CV folds overlap; Bengio & Grandvalet 2004),
        so the best method is only accepted over a simpler one if it has lower error in
        every held-out year.
    """
    from .harmonize import COMPLEXITY_ORDER

    order = [m for m in (order or COMPLEXITY_ORDER) if m in per_year.columns]
    if not order:
        raise ValueError("No candidate methods in per-year scores")
    table = per_year[order].dropna()
    means = table.mean()
    best = means.idxmin()
    if rule == "min":
        return best, f"lowest mean RMSE(log) {means[best]:.3f}"
    if rule != "1se":
        raise ValueError("rule must be '1se' or 'min'")

    k = len(table)
    for m in order:
        if m == best:
            if m == order[0]:
                return best, f"simplest method is also the best (mean RMSE(log) {means[best]:.3f}, {k} years)"
            return best, f"best mean RMSE(log) {means[best]:.3f}; clearly better than simpler methods ({k} years)"
        diff = table[m] - table[best]
        if k >= min_years_for_se:
            se = diff.std(ddof=1) / np.sqrt(k)
            if diff.mean() <= se:
                return m, (f"1-SE rule: {m} within one paired SE of best {best} "
                           f"(+{diff.mean():.3f} <= {se:.3f}, {k} years)")
        elif not (diff > 0).all():
            return m, (f"few years ({k}): {best} does not beat simpler {m} in every year "
                       f"(wins {int((diff > 0).sum())}/{k})")
    return best, "fallback"


def overlap_drift(pairs: pd.DataFrame, model) -> dict:
    """Annual mean log ratio pred/obs on the fit pairs and its linear trend per year.

    A clear trend means the donor/reference relationship is changing (e.g. orbit drift)
    and the fit window should be shortened.
    """
    pred = model(pairs["x"].to_numpy(float), pairs["mon"].to_numpy())
    r = pd.Series(np.log1p(pred) - np.log1p(pairs["y"].to_numpy(float)), index=pairs.index)
    annual = r.groupby(pairs["year"]).mean()
    slope = float(np.polyfit(annual.index, annual.values, 1)[0]) if len(annual) >= 3 else np.nan
    return {"slope_log_per_year": slope, "annual_mean_log_ratio": {int(k): float(v) for k, v in annual.items()}}


def pettitt(values) -> dict:
    """Pettitt (1979) change-point test. Returns the last index before the change, K and approx. p."""
    x = np.asarray(values, float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 3:
        return {"index": None, "K": np.nan, "p": np.nan}
    ranks = pd.Series(x).rank().to_numpy()
    t = np.arange(1, n + 1)
    u = 2 * np.cumsum(ranks) - t * (n + 1)
    k_idx = int(np.argmax(np.abs(u[:-1])))
    K = float(abs(u[k_idx]))
    p = float(min(1.0, 2 * np.exp(-6 * K**2 / (n**3 + n**2))))
    return {"index": k_idx, "K": K, "p": p}


def deseasonalized_log(series: pd.Series) -> pd.Series:
    """log1p counts minus their calendar-month mean (PeriodIndex series)."""
    lv = np.log1p(series.astype(float))
    return lv - lv.groupby(series.index.month).transform("mean")


def step_at(series: pd.Series, at, years: int = 2) -> float:
    """Mean deseasonalized log level in the `years` after `at` minus the `years` before."""
    at = pd.Period(at, "M")
    d = deseasonalized_log(series).dropna()
    before = d[(d.index >= at - 12 * years) & (d.index < at)]
    after = d[(d.index >= at) & (d.index < at + 12 * years)]
    if len(before) < 6 or len(after) < 6:
        return np.nan
    return float(after.mean() - before.mean())


def source_switches(source: pd.Series) -> list[pd.Period]:
    """Months where the harmonized series changes source (the potential seams)."""
    s = source[source != "no data"]
    changed = s.ne(s.shift()) & s.shift().notna()
    return list(s.index[changed])


def seam_tests(series: pd.Series, seams, years: int = 2, guard_months: int = 24) -> pd.DataFrame:
    """Step at each seam vs a placebo distribution of steps at every other January.

    `placebo_pct` = share of placebo |steps| smaller than the seam's |step|. A seam that is
    larger than ~95 % of placebo steps is suspicious; real fire variability (El Nino
    years) also produces large steps, which is why the placebo comparison matters.
    """
    seams = [pd.Period(s, "M") for s in seams]
    s = series.dropna()
    if s.empty:
        return pd.DataFrame()
    placebo_dates = [p for p in pd.period_range(s.index.min() + 12 * years, s.index.max() - 12 * years, freq="M")
                     if p.month == 1 and all(abs((p - x).n) > guard_months for x in seams)]
    placebo = np.array([abs(step_at(series, p, years)) for p in placebo_dates], float)
    placebo = placebo[~np.isnan(placebo)]
    rows = []
    for seam in seams:
        st = step_at(series, seam, years)
        pct = float(np.mean(placebo < abs(st))) if len(placebo) and not np.isnan(st) else np.nan
        rows.append({"seam": str(seam), "step_log": st, "step_pct": 100 * (np.exp(st) - 1) if not np.isnan(st) else np.nan,
                     "placebo_pct": pct, "n_placebo": len(placebo)})
    return pd.DataFrame(rows)
