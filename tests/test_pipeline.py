"""End-to-end checks on synthetic demo data (not findings - just that the pipeline behaves)."""

import json
from datetime import date

import numpy as np
import pandas as pd
import pytest

from burncal.benchmark import step_at
from burncal.config import Settings
from burncal.pipeline import naive_series, run, write_outputs


@pytest.fixture(scope="module")
def result(demo_raw):
    return run(demo_raw, Settings())


def test_chain_applies_expected_steps(result):
    steps = {s.donor: s for s in result.harmonization.steps}
    assert steps["SNPP"].status == "applied"
    assert steps["Aqua+Terra"].status == "applied"
    assert steps["Aqua+Terra"].method.count("+") == 1  # one method per route
    assert steps["Aqua"].status == "skipped"  # demo Aqua never flies without Terra
    assert steps["Terra"].status == "applied"
    assert steps["Terra"].months_filled == 20  # 2000-11 .. 2002-06
    assert steps["NOAA21"].status == "skipped"  # NOAA-20 never missing in demo data


def test_series_is_complete_and_labelled(result):
    f = result.harmonization.frame
    assert f["harmonized"].notna().all()
    assert (f["lower"] <= f["harmonized"] + 1e-9).all() and (f["harmonized"] <= f["upper"] + 1e-9).all()
    assert f.loc[pd.Period("2001-06", "M"), "source"].startswith("Terra converted")
    assert f.loc[pd.Period("2008-06", "M"), "source"].startswith("Aqua+Terra converted")
    assert f.loc[pd.Period("2015-06", "M"), "source"].startswith("SNPP converted")
    assert f.loc[pd.Period("2020-06", "M"), "source"] == "NOAA20 measured"
    # measured months carry no band
    m = f["source"] == "NOAA20 measured"
    assert (f.loc[m, "lower"] == f.loc[m, "harmonized"]).all()


def test_2012_jump_removed(result):
    naive = naive_series(result.monthly)
    assert step_at(naive, "2012-01") > 0.8
    assert abs(step_at(result.harmonization.series, "2012-01")) < 0.3 * step_at(naive, "2012-01")


def test_demo_aqua_drift_is_visible_outside_fit_window(result):
    # fit window stops in 2020, so the drift check inside the window should be small
    aqua = next(s for s in result.harmonization.steps if s.donor == "Aqua+Terra")
    assert abs(aqua.drift["slope_log_per_year"]) < 0.05


def test_cell_day_conservation(result):
    # every cleaned hotspot lands in exactly one month; cell-days never exceed points
    from burncal.aggregate import monthly_counts
    pts = monthly_counts(result.hotspots, unit="points")
    assert pts.sum().sum() == len(result.hotspots)
    assert (result.monthly.fillna(0) <= pts.fillna(0)).all().all()


def test_write_outputs(result, tmp_path):
    files = write_outputs(result, tmp_path)
    names = {p.name for p in files}
    assert {"harmonized_monthly.csv", "harmonized_annual.csv", "seam_tests.csv", "harmonization_report.json"} <= names
    rep = json.loads((tmp_path / "harmonization_report.json").read_text())
    assert [s["donor"] for s in rep["steps"]] == ["SNPP", "NOAA21", "Aqua+Terra", "Aqua", "Terra"]
    t = pd.read_csv(tmp_path / "harmonized_monthly.csv")
    assert {"harmonized", "lower", "upper", "source", "viirs_satellites_active"} <= set(t.columns)


def test_download_merge_streams_chunks(tmp_path, monkeypatch):
    import download_firms as d
    cache = tmp_path / ".cache" / d.bbox_tag("1,2,3,4") / "SRC"
    cache.mkdir(parents=True)
    hdr = "latitude,longitude,acq_date\n"
    (cache / "2020-12-30_5.csv").write_text(hdr + "1,2,2020-12-30\n1,2,2021-01-02\n")
    (cache / "2021-01-04_5.csv").write_text(hdr + "3,4,2021-01-04")  # no final newline, as FIRMS sends
    (cache / "2021-01-06_5.csv").write_text(hdr + "5,6,2021-01-06\n")
    (cache / "2021-01-09_5.csv").write_text(hdr)  # empty chunk (no fires)
    monkeypatch.setattr(d, "chunks", lambda *a, **k: [])  # nothing to fetch, only merge
    out = d.download_source(None, "KEY", "SRC", "1,2,3,4", date(2020, 12, 30), date(2021, 1, 13), 5, tmp_path, 0)
    names = sorted(p.name for p in out)
    assert names == ["SRC_2020.csv", "SRC_2021.csv"]
    assert (tmp_path / "api" / d.bbox_tag("1,2,3,4") / "SRC_2020.csv").read_text().count("\n") == 3
    lines = (tmp_path / "api" / d.bbox_tag("1,2,3,4") / "SRC_2021.csv").read_text().splitlines()
    assert lines == ["latitude,longitude,acq_date", "3,4,2021-01-04", "5,6,2021-01-06"]


def test_download_chunks():
    from download_firms import chunks, looks_like_csv
    c = list(chunks(date(2020, 1, 1), date(2020, 1, 12), 5))
    assert c == [(date(2020, 1, 1), 5), (date(2020, 1, 6), 5), (date(2020, 1, 11), 2)]
    assert sum(n for _, n in chunks(date(2020, 1, 1), date(2020, 12, 31), 5)) == 366
    assert looks_like_csv("latitude,longitude\n") and not looks_like_csv("Invalid MAP_KEY.")


def test_two_route_step_averages_and_band_covers_both():
    """Aqua slowly loses detections, Terra is stable: the combined value sits between the
    two routes and the band contains both."""
    from burncal.config import FillStep
    from burncal.harmonize import harmonize
    rng = np.random.default_rng(1)
    idx = pd.period_range("2003-01", "2020-12", freq="M")
    truth = pd.Series(1000 * (1 + 0.8 * np.sin(2 * np.pi * idx.month / 12)) * rng.lognormal(0, 0.3, len(idx)), idx)
    years = idx.year - 2012
    monthly = pd.DataFrame({
        "Terra": truth / 5 * rng.lognormal(0, 0.05, len(idx)),
        "Aqua": truth / 4 * np.exp(-0.03 * years) * rng.lognormal(0, 0.05, len(idx)),
        "SNPP": truth.where(idx >= pd.Period("2012-01", "M")),
    })
    s = Settings(reference="SNPP", fill_steps=(FillStep("Aqua+Terra", "2012-01", "2020-12"),))
    res = harmonize(monthly, s)
    st_ = res.steps[0]
    assert st_.status == "applied" and st_.months_filled == 108 and "combined LOYO" in st_.selection
    f = res.frame.loc[: pd.Period("2011-12", "M")]
    via = {}
    for n in ("Aqua", "Terra"):
        r = (monthly.loc["2012-01":, "SNPP"].sum() / monthly.loc["2012-01":, n].sum())
        via[n] = monthly.loc[f.index, n] * r
    lo, hi = np.minimum(via["Aqua"], via["Terra"]), np.maximum(via["Aqua"], via["Terra"])
    assert ((f["harmonized"] >= lo * 0.8) & (f["harmonized"] <= hi * 1.25)).mean() > 0.9
    # band contains both routes (routes here use M1; the step may pick another method, hence the tolerance)
    assert ((f["lower"] <= lo * 1.1) & (f["upper"] >= hi / 1.1)).mean() > 0.9
    # early years: Aqua route over-predicts truth; the combination is closer to it
    early = slice(None, pd.Period("2006-12", "M"))
    err = lambda p: abs(np.log(p.loc[early].sum() / truth.loc[early].sum()))
    assert err(f["harmonized"]) < err(via["Aqua"])


def test_annual_ranges(result):
    a = result.harmonization.annual()
    assert (a["months"] == 12).all() and a.index.is_monotonic_increasing
    measured = a[a["estimated_share"] == 0]
    assert len(measured) and (measured["sd_log"] == 0).all() and (measured["lower"] == measured["total"]).all()
    conv = a[a["estimated_share"] == 1]
    assert len(conv) and (conv["lower"] < conv["total"]).all() and (conv["total"] < conv["upper"]).all()
    # annual ranges are much narrower than summed monthly bounds (monthly errors cancel within a year)
    f = result.harmonization.frame
    summed = f.groupby(f.index.year)[["lower", "upper"]].sum().loc[conv.index]
    assert ((conv["upper"] - conv["lower"]) < (summed["upper"] - summed["lower"])).mean() > 0.8
    st_ = next(s for s in result.harmonization.steps if s.donor == "Aqua+Terra")
    assert st_.annual_error["n"] > 10 and st_.annual_error["a2"] >= 0 and st_.annual_error["b2"] >= 0


def test_annual_error_grows_with_distance():
    """A donor whose ratio drifts over time: older years get wider annual ranges."""
    from burncal.config import FillStep
    from burncal.harmonize import harmonize
    rng = np.random.default_rng(3)
    idx = pd.period_range("2000-01", "2020-12", freq="M")
    truth = pd.Series(1000 * (1 + 0.8 * np.sin(2 * np.pi * idx.month / 12)) * rng.lognormal(0, 0.2, len(idx)), idx)
    drift = np.exp(0.04 * (idx.year - 2012) + rng.normal(0, 0.05, len(idx)))
    monthly = pd.DataFrame({"D": truth / 4 * drift, "R": truth.where(idx >= pd.Period("2010-01", "M"))})
    res = harmonize(monthly, Settings(reference="R", fill_steps=(FillStep("D", "2010-01", "2020-12", method="M1"),)))
    a = res.annual()
    assert res.steps[0].annual_error["b2"] > 0
    assert a.loc[2000, "sd_log"] > a.loc[2008, "sd_log"] > 0


def test_annual_range_contains_each_route():
    """Aqua and Terra routes drift apart (as in Vietnam): the yearly range must contain the
    year's total by each single route, not only the error-model interval."""
    from burncal.config import FillStep
    from burncal.harmonize import harmonize
    rng = np.random.default_rng(5)
    idx = pd.period_range("2003-01", "2020-12", freq="M")
    truth = pd.Series(1000 * (1 + 0.8 * np.sin(2 * np.pi * idx.month / 12)) * rng.lognormal(0, 0.2, len(idx)), idx)
    years = idx.year - 2012
    monthly = pd.DataFrame({
        "Aqua": truth / 4 * rng.lognormal(0, 0.05, len(idx)),
        "Terra": truth / 8 * np.exp(0.08 * years) * rng.lognormal(0, 0.05, len(idx)),
        "SNPP": truth.where(idx >= pd.Period("2012-01", "M")),
    })
    res = harmonize(monthly, Settings(reference="SNPP", fill_steps=(FillStep("Aqua+Terra", "2012-01", "2020-12"),)))
    f, a = res.frame, res.annual()
    assert {"route[Aqua+Terra]:Aqua", "route[Aqua+Terra]:Terra"} <= set(f.columns)
    early = a.loc[2003:2011]
    for col in ("route[Aqua+Terra]:Aqua", "route[Aqua+Terra]:Terra"):
        r = f[col].groupby(f.index.year).sum().loc[early.index]
        assert ((early["lower"] <= r * (1 + 1e-9)) & (r <= early["upper"] * (1 + 1e-9))).all()
    assert (early["lower"] <= early["total"]).all() and (early["total"] <= early["upper"]).all()
    measured = a[a["estimated_share"] == 0]
    assert (measured["lower"] == measured["total"]).all()  # measured years still have no range


def test_too_few_fires_leaves_months_empty():
    """A tiny area where the donor almost never sees a fire: no conversion is learned and the
    months stay empty instead of being filled with a guess."""
    from burncal.config import FillStep
    from burncal.harmonize import harmonize
    rng = np.random.default_rng(7)
    idx = pd.period_range("2003-01", "2020-12", freq="M")
    ref = pd.Series(rng.poisson(0.8, len(idx)), idx, dtype=float)
    donor = pd.Series(0.0, idx)
    donor.iloc[[5, 40, 100, 150]] = 1.0  # 4 months with a fire
    monthly = pd.DataFrame({"D": donor, "R": ref.where(idx >= pd.Period("2012-01", "M"))})
    res = harmonize(monthly, Settings(reference="R", fill_steps=(FillStep("D", "2012-01", "2020-12"),)))
    st_ = res.steps[0]
    assert st_.status == "skipped" and st_.reason.startswith("too few fires")
    assert res.series.loc[: pd.Period("2011-12", "M")].isna().all()
    assert res.series.loc[pd.Period("2012-01", "M"):].notna().all()
    # same data with enough fire months is converted
    donor2 = pd.Series(rng.poisson(3, len(idx)), idx, dtype=float)
    res2 = harmonize(monthly.assign(D=donor2), Settings(reference="R", fill_steps=(FillStep("D", "2012-01", "2020-12"),)))
    assert res2.steps[0].status == "applied"
