import numpy as np
import pandas as pd

from burncal.benchmark import evaluate, loyo_benchmark, overlap_drift, pettitt, seam_tests, step_at
from burncal.calendar import anomaly_pct, anomaly_z, season_to_date, to_grid
from burncal.harmonize import METHODS, make_pairs


def synthetic_pairs(ratio=4.0, n_years=8, noise=0.1, seed=0, drift=0.0):
    rng = np.random.default_rng(seed)
    idx = pd.period_range("2012-01", periods=12 * n_years, freq="M")
    season = 1 + 2 * np.exp(-((idx.month - 8.5) ** 2) / 3)
    x = pd.Series(rng.poisson(50 * season) + 1.0, index=idx)
    years = idx.year - idx.year.min()
    y = pd.Series(x.to_numpy() * ratio * np.exp(rng.normal(0, noise, len(idx)) + drift * years), index=idx)
    return x, y


def test_m1_recovers_constant_ratio():
    x, y = synthetic_pairs(ratio=4.0, noise=0.0)
    model = METHODS["M1"](make_pairs(x, y))
    assert np.allclose(model(np.array([10.0]), np.array([1])), 40.0)


def test_m3_smearing_removes_back_transform_bias():
    x, y = synthetic_pairs(ratio=4.0, noise=0.5, seed=3)
    pairs = make_pairs(x, y)
    pred = METHODS["M3"](pairs)(pairs["x"].to_numpy(), pairs["mon"].to_numpy())
    assert abs(evaluate(pred, pairs["y"])["bias_pct"]) < 5


def test_m4_recovers_nonlinear_monotone_relation():
    # y = 3 * x^1.2: a constant ratio cannot fit this, quantile mapping can
    x, _ = synthetic_pairs(noise=0.0)
    y = 3 * x ** 1.2
    pairs = make_pairs(x, y)
    xin, mon = pairs["x"].to_numpy(), pairs["mon"].to_numpy()
    m4 = evaluate(METHODS["M4"](pairs)(xin, mon), pairs["y"])
    m1 = evaluate(METHODS["M1"](pairs)(xin, mon), pairs["y"])
    assert m4["RMSE_log"] < 0.02
    assert m4["RMSE_log"] < m1["RMSE_log"] / 5


def test_m4_extrapolates_monotonically_and_finitely():
    x, y = synthetic_pairs(ratio=4.0, noise=0.1)
    pairs = make_pairs(x, y)
    model = METHODS["M4"](pairs)
    probe = np.array([0.0, 1.0, pairs["x"].min(), pairs["x"].median(), pairs["x"].max(), 10 * pairs["x"].max()])
    out = model(probe, np.ones(len(probe), int))
    assert np.all(np.isfinite(out)) and np.all(out >= 0)
    assert np.all(np.diff(out) >= -1e-9)  # monotone
    # beyond the range: keeps the top-end ratio (~4x), no cap, no explosion
    assert 2 < out[-1] / probe[-1] < 8


def test_m4_matches_target_distribution():
    x, y = synthetic_pairs(ratio=4.0, noise=0.3, seed=5)
    pairs = make_pairs(x, y)
    pred = METHODS["M4"](pairs)(pairs["x"].to_numpy(), pairs["mon"].to_numpy())
    for q in (0.1, 0.5, 0.9):
        assert abs(np.log1p(np.quantile(pred, q)) - np.log1p(np.quantile(pairs["y"], q))) < 0.1


def test_m4_handles_many_zero_months_and_small_samples():
    idx = pd.period_range("2012-01", periods=36, freq="M")
    x = pd.Series(np.r_[np.zeros(18), np.arange(1, 19)], index=idx, dtype=float)
    y = x * 4
    model = METHODS["M4"](make_pairs(x, y))
    assert np.isfinite(model(np.array([0.0, 5.0]), np.array([1, 1]))).all()
    small = make_pairs(x.iloc[:6], y.iloc[:6] + 1)  # < 12 months -> falls back to M3
    assert np.isfinite(METHODS["M4"](small)(np.array([3.0]), np.array([1]))).all()


def _per_year(rows: dict) -> pd.DataFrame:
    """rows = {method: [rmse per year]} -> per-year table like per_year_rmse returns."""
    n = len(next(iter(rows.values())))
    return pd.DataFrame(rows, index=pd.Index(range(2012, 2012 + n), name="year"))


def test_1se_prefers_simple_when_gain_is_noise():
    from burncal.benchmark import select_method
    rng = np.random.default_rng(0)
    base = rng.uniform(0.1, 0.3, 10)
    noise = rng.normal(0, 0.02, 10)
    noise -= noise.mean()  # mean gain exactly 0.002, spread 0.02 -> SE ~0.006
    t = _per_year({"M1": base, "M4": base - 0.002 + noise})  # tiny, noisy gain
    m, why = select_method(t)
    assert m == "M1" and "1-SE" in why
    assert select_method(t, rule="min")[0] == t.mean().idxmin()


def test_1se_accepts_complex_when_clearly_better():
    from burncal.benchmark import select_method
    base = np.linspace(0.2, 0.4, 10)
    t = _per_year({"M1": base, "M3": base - 0.01, "M4": base - 0.08 + np.r_[0.01, -0.01] .repeat(5)})
    assert select_method(t)[0] == "M4"


def test_paired_differences_ignore_shared_year_difficulty():
    from burncal.benchmark import select_method
    # years differ hugely in difficulty, but M2 is better by 0.05 in every single year
    hard = np.array([0.1, 0.9, 0.2, 1.5, 0.3, 0.8])
    t = _per_year({"M1": hard + 0.05, "M2": hard})
    assert select_method(t)[0] == "M2"


def test_few_years_requires_win_every_year():
    from burncal.benchmark import select_method
    t = _per_year({"M1": [0.30, 0.30, 0.30], "M4": [0.20, 0.25, 0.35]})  # wins 2/3
    m, why = select_method(t)
    assert m == "M1" and "2/3" in why
    t = _per_year({"M1": [0.30, 0.30, 0.30], "M4": [0.20, 0.25, 0.29]})  # wins 3/3
    assert select_method(t)[0] == "M4"


def test_order_respected_simplest_first():
    from burncal.benchmark import select_method
    t = _per_year({"M4": [0.2] * 6, "M3": [0.2] * 6, "M1": [0.2] * 6})  # all tied
    assert select_method(t)[0] == "M1"


def test_make_pairs_window():
    x, y = synthetic_pairs()
    p = make_pairs(x, y, "2014-01", "2015-12")
    assert len(p) == 24 and set(p["year"]) == {2014, 2015}


def test_loyo_prefers_harmonization_over_m0():
    x, y = synthetic_pairs()
    summary, preds = loyo_benchmark(make_pairs(x, y))
    assert summary.index[-1] == "M0"
    assert set(preds["method"]) == set(METHODS)


def test_overlap_drift_detects_trend():
    x, y = synthetic_pairs(drift=-0.08, noise=0.02)
    pairs = make_pairs(x, y)
    d = overlap_drift(pairs, METHODS["M1"](pairs))
    assert d["slope_log_per_year"] > 0.05  # predictions rise relative to a falling target
    x, y = synthetic_pairs(drift=0.0, noise=0.02)
    pairs = make_pairs(x, y)
    assert abs(overlap_drift(pairs, METHODS["M1"](pairs))["slope_log_per_year"]) < 0.01


def test_pettitt_finds_step():
    rng = np.random.default_rng(1)
    v = np.r_[rng.normal(0, 1, 60), rng.normal(3, 1, 60)]
    r = pettitt(v)
    assert 55 <= r["index"] <= 62 and r["p"] < 0.01
    assert pettitt(rng.normal(0, 1, 120))["p"] > 0.05


def test_step_and_seam_tests():
    idx = pd.period_range("2000-01", "2020-12", freq="M")
    rng = np.random.default_rng(2)
    base = 100 * np.exp(rng.normal(0, 0.2, len(idx)))
    jumped = pd.Series(np.where(idx >= pd.Period("2012-01", "M"), base * 4, base), index=idx)
    flat = pd.Series(base, index=idx)
    assert step_at(jumped, "2012-01") > 1.2
    assert abs(step_at(flat, "2012-01")) < 0.2
    t = seam_tests(jumped, ["2012-01"])
    assert t["placebo_pct"].iloc[0] == 1.0
    assert seam_tests(flat, ["2012-01"])["placebo_pct"].iloc[0] < 0.95


def test_calendar_helpers():
    idx = pd.period_range("2010-01", "2014-06", freq="M")
    s = pd.Series(np.arange(len(idx), dtype=float) + 1, index=idx)
    g = to_grid(s)
    assert g.shape == (5, 12) and np.isnan(g.loc[2014, 7])
    z = anomaly_z(g, (2010, 2013))
    assert np.isclose(z.loc[2010:2013].mean().mean(), 0, atol=1e-9)
    pct = anomaly_pct(g, (2010, 2013))
    assert pct.loc[2014, 1] > 0
    std = season_to_date(s, 2014)
    assert std.attrs["through_month"] == 6
    assert std.loc[2014, "rank"] == 1  # values increase every month, so 2014 is highest
