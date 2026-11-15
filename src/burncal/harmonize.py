"""Harmonization methods and the reference-filling chain.

Every method is fitted on a `pairs` table (columns x = donor counts, y = reference
counts, mon = calendar month, year) and returns `predict(x, mon) -> np.ndarray`.

M0  no harmonization (donor counts as they are)
M1  one constant ratio  sum(y) / sum(x)
M2  one ratio per calendar month (falls back to M1 for months without donor counts)
M3  log-linear  log1p(y) = a + b log1p(x), back-transformed with Duan's smearing
    correction (a plain expm1 back-transform underestimates on average)
M4  quantile mapping: a donor month at the p-th percentile of the donor's distribution
    becomes the p-th percentile of the reference's distribution (empirical CDFs on
    log1p counts). Captures non-linear sensor gaps (e.g. VIIRS sees relatively more in
    quiet months, when fires are small) without assuming a functional form.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from .config import FillStep, Settings

Predictor = Callable[[np.ndarray, np.ndarray], np.ndarray]


def _xym(pairs: pd.DataFrame):
    return (pairs["x"].to_numpy(float), pairs["y"].to_numpy(float), pairs["mon"].to_numpy(int))


def _ratio(x: np.ndarray, y: np.ndarray) -> float:
    return float(y.sum() / x.sum()) if x.sum() > 0 else 1.0


def fit_m0(pairs: pd.DataFrame) -> Predictor:
    return lambda x, mon: np.asarray(x, float)


def fit_m1(pairs: pd.DataFrame) -> Predictor:
    x, y, _ = _xym(pairs)
    r = _ratio(x, y)
    return lambda x, mon: np.asarray(x, float) * r


def fit_m2(pairs: pd.DataFrame) -> Predictor:
    x, y, m = _xym(pairs)
    overall = _ratio(x, y)
    ratios = np.full(13, overall)
    for k in range(1, 13):
        sel = m == k
        if x[sel].sum() > 0:
            ratios[k] = y[sel].sum() / x[sel].sum()
    return lambda x, mon: np.asarray(x, float) * ratios[np.asarray(mon, int)]


def fit_m3(pairs: pd.DataFrame) -> Predictor:
    x, y, _ = _xym(pairs)
    lx, ly = np.log1p(x), np.log1p(y)
    if len(x) < 3 or np.ptp(lx) == 0:
        return fit_m1(pairs)
    b, a = np.polyfit(lx, ly, 1)
    smear = float(np.mean(np.exp(ly - (a + b * lx))))

    def predict(x, mon):
        return np.maximum(np.exp(a + b * np.log1p(np.asarray(x, float))) * smear - 1, 0.0)

    return predict


def fit_m4(pairs: pd.DataFrame, n_quantiles: int = 101, min_months: int = 12) -> Predictor:
    """Empirical quantile mapping on log1p counts.

    Transfer function: matched quantiles (q_x(p), q_y(p)) for p in [0, 1], linearly
    interpolated. Tied donor quantiles (e.g. many zero months) are averaged so the
    mapping stays a function. Outside the training range the correction at the nearest
    end is held constant in log space (i.e. a constant ratio), so new record months are
    neither capped nor blown up. Falls back to M3 with fewer than `min_months` pairs.
    """
    x, y, _ = _xym(pairs)
    if len(x) < min_months:
        return fit_m3(pairs)
    probs = np.linspace(0, 1, min(n_quantiles, len(x)))
    qx = np.quantile(np.log1p(x), probs)
    qy = np.quantile(np.log1p(y), probs)
    ux, inv = np.unique(qx, return_inverse=True)
    uy = np.bincount(inv, weights=qy) / np.bincount(inv)
    if len(ux) < 2:
        return fit_m1(pairs)
    lo_shift, hi_shift = uy[0] - ux[0], uy[-1] - ux[-1]

    def predict(x, mon):
        lx = np.log1p(np.asarray(x, float))
        out = np.interp(lx, ux, uy)
        out = np.where(lx < ux[0], lx + lo_shift, out)
        out = np.where(lx > ux[-1], lx + hi_shift, out)
        return np.maximum(np.expm1(out), 0.0)

    return predict


METHODS: dict[str, Callable[[pd.DataFrame], Predictor]] = {
    "M0": fit_m0, "M1": fit_m1, "M2": fit_m2, "M3": fit_m3, "M4": fit_m4,
}
METHOD_LABELS = {
    "M0": "No harmonization", "M1": "Constant ratio", "M2": "Monthly ratio",
    "M3": "Log-linear (smearing)", "M4": "Quantile mapping",
}
# Simplest first, by number of fitted parameters: M1 = 1 ratio, M3 = 2 coefficients
# (+ smearing factor), M2 = 12 ratios, M4 = ~100 quantile pairs (non-parametric).
# M0 is the "do nothing" baseline and is never selected.
COMPLEXITY_ORDER: tuple[str, ...] = ("M1", "M3", "M2", "M4")


def make_pairs(x: pd.Series, y: pd.Series, start: str | None = None, end: str | None = None) -> pd.DataFrame:
    """Overlapping months of donor `x` and target `y` inside [start, end] (Period index)."""
    df = pd.DataFrame({"x": x, "y": y}).dropna()
    if start:
        df = df[df.index >= pd.Period(start, "M")]
    if end:
        df = df[df.index <= pd.Period(end, "M")]
    df["mon"] = df.index.month
    df["year"] = df.index.year
    return df


@dataclass
class StepReport:
    donor: str
    status: str  # "applied" | "skipped"
    reason: str = ""
    method: str = ""
    selection: str = ""  # why this method was chosen
    n_pairs: int = 0
    months_filled: int = 0
    fit_window: tuple = ()
    interval_log: tuple = ()  # (low, high) quantiles of log1p residuals
    holdout: pd.DataFrame | None = None
    loyo: pd.DataFrame | None = None
    drift: dict = field(default_factory=dict)
    annual_error: dict = field(default_factory=dict)  # sd(d) = sqrt(a2 + b2 d^2) of annual log errors
    note: str = ""

    def to_dict(self) -> dict:
        d = {k: v for k, v in self.__dict__.items() if k not in {"holdout", "loyo"}}
        d["fit_window"] = list(self.fit_window)
        d["interval_log"] = [float(v) for v in self.interval_log]
        return d


@dataclass
class HarmonizationResult:
    frame: pd.DataFrame  # harmonized, lower, upper, source + raw platform columns
    steps: list[StepReport]

    @property
    def series(self) -> pd.Series:
        return self.frame["harmonized"]

    def annual(self, z: float = 1.645) -> pd.DataFrame:
        """Calendar-year totals with a likely range (default 90 %), complete years only.

        The range comes from each step's annual error model (backcast + leave-one-year-out
        errors of annual totals), not from summing monthly bounds: monthly errors largely
        cancel within a year, so summed bounds are several times too wide. Converted
        months are weighted by their share of the year; measured months add no error.
        Where a step averages several routes (e.g. Aqua+Terra), the range is widened so it
        always contains the year's total by each single route, the same rule as the monthly
        band (backcast coverage 92.6 % -> 96.3 %, Vietnam 6/9 -> 9/9; docs/decisions.md).
        """
        f = self.frame
        g = f.groupby(f.index.year)
        tot = g["harmonized"].sum(min_count=1)
        n = g["harmonized"].count()
        share = (f["harmonized"] * f["annual_sd_log"]).groupby(f.index.year).sum() / tot.replace(0, np.nan)
        sd = share.fillna(0.0)
        est = (~f["source"].str.endswith("measured") & f["harmonized"].notna()).groupby(f.index.year).mean()
        lower, upper = tot * np.exp(-z * sd), tot * np.exp(z * sd)
        # converted months without an annual error estimate: fall back to the (wide) summed monthly bounds
        unknown = (f["annual_sd_log"].isna() & f["harmonized"].notna()).groupby(f.index.year).any()
        if unknown.any():
            lower = lower.where(~unknown, g["lower"].sum(min_count=1))
            upper = upper.where(~unknown, g["upper"].sum(min_count=1))
            sd = sd.where(~unknown.reindex(sd.index, fill_value=False))
        for col in [c for c in f.columns if c.startswith("route[")]:
            alt = tot - f["harmonized"].where(f[col].notna()).groupby(f.index.year).sum()                 + f[col].groupby(f.index.year).sum()
            lower, upper = np.minimum(lower, alt), np.maximum(upper, alt)
        out = pd.DataFrame({"total": tot, "lower": lower, "upper": upper,
                            "sd_log": sd, "estimated_share": est, "months": n})
        out.index.name = "year"
        return out[out["months"] == 12]


def harmonize(monthly: pd.DataFrame, settings: Settings | None = None) -> HarmonizationResult:
    """Build one reference-equivalent series by filling the reference with converted donors.

    The reference platform's own months are kept as measured. Each FillStep then fills
    the still-missing months that its donor covers, using the method chosen by
    leave-one-year-out cross-validation inside the step's fit window. Converted months
    get an empirical uncertainty band from the cross-validation residuals.
    """
    s = settings or Settings()
    if s.reference not in monthly:
        raise KeyError(f"Reference platform {s.reference!r} has no data. Columns: {list(monthly.columns)}")

    series = monthly[s.reference].astype(float).copy()
    lower, upper = series.copy(), series.copy()
    annual_sd = pd.Series(np.where(series.notna(), 0.0, np.nan), index=monthly.index)
    source = pd.Series(np.where(series.notna(), f"{s.reference} measured", ""), index=monthly.index, dtype=object)
    reports: list[StepReport] = []
    route_cols: dict[str, pd.Series] = {}  # "route[Aqua+Terra]:Aqua" -> that route's conversion
    q = ((1 - s.interval) / 2, 1 - (1 - s.interval) / 2)

    for step in s.fill_steps:
        rep = StepReport(donor=step.donor, status="skipped", fit_window=(step.fit_start, step.fit_end), note=step.note)
        reports.append(rep)
        names = step.donor.split("+")
        missing = [n for n in names if n not in monthly]
        if missing:
            rep.reason = f"no data for donor {', '.join(missing)}" if len(names) > 1 else "no data for donor"
            continue
        to_fill = series.isna() & monthly[names].notna().all(axis=1)
        if not to_fill.any():
            rep.reason = "nothing to fill"
            continue
        methods = step.method.split("+") if "+" in step.method else [step.method] * len(names)
        if len(methods) != len(names):
            raise ValueError(f"FillStep {step.donor!r}: method {step.method!r} needs one method per donor")
        routes = []
        for n, meth in zip(names, methods):
            r = _fit_route(monthly[n], series, step, s, meth)
            if isinstance(r, str):
                rep.reason = r if len(names) == 1 else f"{n}: {r}"
                break
            routes.append(r)
        else:
            preds = _apply_routes(rep, names, routes, monthly, to_fill, series, lower, upper, source, q)
            if len(names) > 1:
                for i, n in enumerate(names):
                    col = route_cols.setdefault(f"route[{step.donor}]:{n}", pd.Series(np.nan, index=monthly.index))
                    col[to_fill] = np.expm1(preds[:, i])
            model = _annual_error_model(names, routes, monthly)
            rep.annual_error = model
            annual_sd[to_fill] = _annual_sd(model, to_fill[to_fill].index, routes)
    
    frame = pd.DataFrame({
        "harmonized": series, "lower": lower, "upper": upper,
        "source": source.replace("", "no data"), "annual_sd_log": annual_sd,
    })
    for col in monthly.columns:
        frame[f"raw_{col}"] = monthly[col]
    for col, v in route_cols.items():
        frame[col] = v
    return HarmonizationResult(frame=frame, steps=reports)


def _fit_route(donor: pd.Series, series: pd.Series, step: FillStep, s: Settings, method: str = "best"):
    """Fit one donor -> reference conversion inside the step's window.

    Returns a dict (pairs, method, selection, loyo, holdout, model, loyo_pred) or a reason string.
    """
    from .benchmark import holdout_benchmark, loyo_benchmark, per_year_rmse, select_method

    pairs = make_pairs(donor, series, step.fit_start, step.fit_end)
    if len(pairs) < s.min_pairs or pairs["year"].nunique() < 2:
        return f"only {len(pairs)} overlapping months in fit window"
    n_fire = int(((pairs["x"] > 0) & (pairs["y"] > 0)).sum())
    if n_fire < s.min_fire_pairs:
        return (f"too few fires: only {n_fire} months where both {donor.name or 'donor'} and the reference "
                f"saw fires (need {s.min_fire_pairs})")
    loyo_scores, loyo_preds = loyo_benchmark(pairs)
    if method == "best":
        method, selection = select_method(
            per_year_rmse(loyo_preds), rule=s.selection_rule, min_years_for_se=s.min_years_for_se)
    else:
        selection = "fixed in the chain (chosen by backcast, see docs/decisions.md)"
    chosen = loyo_preds.loc[loyo_preds["method"] == method]
    return {"pairs": pairs, "method": method, "selection": selection, "loyo": loyo_scores,
            "holdout": holdout_benchmark(pairs, s.holdout_years), "model": METHODS[method](pairs),
            "loyo_pred": chosen[["year", "pred", "obs"]]}


def _apply_routes(rep, names, routes, monthly, to_fill, series, lower, upper, source, q) -> np.ndarray:
    """Fill `to_fill` months with the log-space mean of the routes' conversions.

    Returns the per-route log1p predictions (months x routes)."""
    from .benchmark import overlap_drift

    months = to_fill[to_fill].index.month.to_numpy()
    preds = np.column_stack([np.log1p(r["model"](monthly[n][to_fill].to_numpy(float), months))
                             for n, r in zip(names, routes)])
    lp = preds.mean(axis=1)

    # out-of-sample residuals of the combination: months held out in every route's LOYO
    lp_cv = pd.concat([np.log1p(r["loyo_pred"]["pred"]).rename(n) for n, r in zip(names, routes)], axis=1).dropna()
    obs = routes[0]["loyo_pred"]["obs"].reindex(lp_cv.index)
    resid = np.log1p(obs.to_numpy(float)) - lp_cv.mean(axis=1).to_numpy()
    lo_q, hi_q = (np.quantile(resid, q) if len(resid) else (0.0, 0.0))

    if len(routes) == 1:
        r = routes[0]
        rep.method, rep.selection, rep.loyo, rep.holdout = r["method"], r["selection"], r["loyo"], r["holdout"]
        rep.n_pairs = len(r["pairs"])
        rep.drift = overlap_drift(r["pairs"], r["model"])
    else:
        rep.method = "+".join(r["method"] for r in routes)
        rep.selection = "; ".join(f"{n}: {r['method']}, {r['selection']}" for n, r in zip(names, routes))
        rmse_comb = float(np.sqrt(np.mean(resid ** 2))) if len(resid) else np.nan
        rep.selection += f"; combined LOYO RMSE(log) {rmse_comb:.3f}"
        rep.loyo = pd.concat([r["loyo"].assign(route=n) for n, r in zip(names, routes)])
        rep.holdout = pd.concat([r["holdout"].assign(route=n) for n, r in zip(names, routes)
                                 if r["holdout"] is not None and not r["holdout"].empty] or [pd.DataFrame()])
        common = routes[0]["pairs"].index
        for r in routes[1:]:
            common = common.intersection(r["pairs"].index)
        rep.n_pairs = len(common)
        cp = routes[0]["pairs"].loc[common]
        xs = {n: monthly[n].reindex(common).to_numpy(float) for n in names}

        def combined(_x, mon, _xs=xs, _routes=routes):  # the combination as a predictor on the common pairs
            return np.expm1(np.mean([np.log1p(r["model"](_xs[n], mon)) for n, r in zip(names, _routes)], axis=0))
        rep.drift = overlap_drift(cp, combined)

    series[to_fill] = np.expm1(lp)
    # band: the empirical interval, widened so it always contains every single route's answer
    lower[to_fill] = np.maximum(np.expm1(np.minimum(lp + lo_q, preds.min(axis=1))), 0)
    upper[to_fill] = np.expm1(np.maximum(lp + hi_q, preds.max(axis=1)))
    source[to_fill] = f"{'+'.join(names)} converted ({rep.method})"
    rep.status, rep.months_filled = "applied", int(to_fill.sum())
    return preds


def _combined_pred(names, routes, monthly, train_idx, test_idx) -> np.ndarray:
    """log1p of the log-mean combination, each route refitted on `train_idx` months."""
    out = []
    for n, r in zip(names, routes):
        tr = r["pairs"].loc[train_idx]
        model = METHODS[r["method"]](tr)
        out.append(np.log1p(model(monthly[n].reindex(test_idx).to_numpy(float), test_idx.month.to_numpy())))
    return np.mean(out, axis=0)


def _annual_error_model(names, routes, monthly, min_fit_years: int = 3) -> dict:
    """How wrong are annual totals of this step, as a function of distance from the fit window?

    Annual log errors log(sum obs / sum pred) are collected (a) leave-one-year-out (distance 0)
    and (b) by backcasting: refit on years >= k, predict whole years < k (distance = years
    from mid-year to the start of the refit window). Then sd(d)^2 = a2 + b2 * d^2 is fitted
    by least squares on the squared errors. Returns {"a2", "b2", "n", "max_d"}; with too few
    years it falls back to the annual LOYO mean square (b2 = 0).
    """
    common = routes[0]["pairs"].index
    for r in routes[1:]:
        common = common.intersection(r["pairs"].index)
    pairs = routes[0]["pairs"].loc[common]
    y = pairs["y"]
    full = pairs.groupby("year").size()
    years = [int(v) for v in full.index if full[v] == 12]
    rows = []
    for yr in years:  # leave-one-year-out, annual
        tr, te = common[pairs["year"] != yr], common[pairs["year"] == yr]
        if len(tr) >= 12:
            p = np.expm1(_combined_pred(names, routes, monthly, tr, te)).sum()
            rows.append((0.0, np.log(y.loc[te].sum() / p) if p > 0 and y.loc[te].sum() > 0 else np.nan))
    for k in years[1:]:  # backcast
        tr = common[pairs["year"] >= k]
        if pairs.loc[tr, "year"].nunique() < min_fit_years:
            continue
        for yr in [v for v in years if v < k]:
            te = common[pairs["year"] == yr]
            p = np.expm1(_combined_pred(names, routes, monthly, tr, te)).sum()
            if p > 0 and y.loc[te].sum() > 0:
                rows.append((k - yr - 0.5, np.log(y.loc[te].sum() / p)))
    e = pd.DataFrame(rows, columns=["d", "r"]).dropna()
    if e.empty:
        return {"a2": np.nan, "b2": 0.0, "n": 0, "max_d": 0.0}
    r2, d2 = e["r"].to_numpy() ** 2, e["d"].to_numpy() ** 2
    if (e["d"] > 0).sum() >= 3:
        A = np.column_stack([np.ones_like(d2), d2])
        a2, b2 = np.linalg.lstsq(A, r2, rcond=None)[0]
        if b2 < 0 or a2 < 0:  # no growth (or growth only) supported: fall back to a constant
            a2, b2 = (float(r2.mean()), 0.0) if b2 < 0 else (0.0, float((r2 * d2).sum() / (d2 ** 2).sum()))
    else:
        a2, b2 = float(r2.mean()), 0.0
    return {"a2": float(a2), "b2": float(b2), "n": int(len(e)), "max_d": float(e["d"].max())}


def _annual_sd(model: dict, months: pd.PeriodIndex, routes) -> np.ndarray:
    """Annual log-error sd for each filled month, from its distance to the fit window."""
    common = routes[0]["pairs"].index
    lo, hi = common.min(), common.max()
    d = np.array([max((lo - m).n, (m - hi).n, 0) for m in months], float) / 12
    if not np.isfinite(model["a2"]):  # no annual error estimate: unknown, not zero
        return np.full(len(d), np.nan)
    return np.sqrt(model["a2"] + model["b2"] * d ** 2)
