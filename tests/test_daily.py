"""Daily tables, user-defined areas and date windows (synthetic data only)."""

import numpy as np
import pandas as pd
import pytest

from burncal import daily as DL
from burncal.config import FillStep, Settings
from burncal.cube import summarize
from burncal.harmonize import harmonize


def _points(n=4000, seed=0):
    rng = np.random.default_rng(seed)
    dates = pd.to_datetime("2019-01-01") + pd.to_timedelta(rng.integers(0, 730, n), unit="D")
    return pd.DataFrame({
        "latitude": rng.uniform(1.0, 2.0, n).round(3), "longitude": rng.uniform(101.0, 102.0, n).round(3),
        "solar_date": dates, "satellite": rng.choice(["NOAA20", "SNPP"], n),
        "country": "MYS", "adm1": rng.choice(["A", "B"], n), "adm2": None, "frp": 1.0,
    })


def test_daily_tables_sum_to_cube_counts():
    p = _points()
    admin, grid = DL.daily_tables(p)
    cube = summarize(p, 0.01)
    a = admin.assign(month=pd.to_datetime(admin["date"]).dt.to_period("M")).groupby(["month", "satellite"])["cell_days"].sum()
    c = cube.groupby(["month", "satellite"])["cell_days"].sum()
    assert a.sort_index().equals(c.sort_index().astype(a.dtype))
    assert grid["cell_days"].sum() == admin["cell_days"].sum()


def test_area_cells():
    keys = DL.box_cells(101.0, 1.0, 102.0, 2.0)
    assert len(keys) == 100 and abs(DL.cells_km2(keys) - 111.32 ** 2 * np.cos(np.radians(1.5))) / 12000 < 0.05
    gy, gx = DL.key_to_cell(DL.cell_key([-5, 3], [1012, -7]))  # round trip, negative values included
    assert list(gy) == [-5, 3] and list(gx) == [1012, -7]
    c = DL.circle_cells(3.1, 101.6, 30)
    assert 0.8 < DL.cells_km2(c) / (np.pi * 30 ** 2) < 1.25
    assert len(DL.circle_cells(3.1, 101.6, 0.5)) == 1  # a tiny circle still covers its own square
    with pytest.raises(ValueError):
        DL.box_cells(102, 1, 101, 2)
    w, s, e, n = DL.cells_extent(keys)
    assert (round(w, 6), round(s, 6), round(e, 6), round(n, 6)) == (101.0, 1.0, 102.0, 2.0)


def test_monthly_from_daily_coverage():
    idx = pd.date_range("2020-01-01", "2020-03-31")
    d = pd.DataFrame({"SNPP": 1.0}, index=idx[::2])
    m = DL.monthly_from_daily(d, {"SNPP": ("2019-11", "2020-03"), "NOAA20": ("2020-02", "2020-03")})
    assert m.loc[pd.Period("2019-12", "M"), "SNPP"] == 0  # flying, no fires
    assert np.isnan(m.loc[pd.Period("2020-01", "M"), "NOAA20"])  # not flying yet
    assert m.loc[pd.Period("2020-01", "M"), "SNPP"] == 16


def _harmonized_with_daily():
    """Two years measured (R) and older years converted from D, with daily data for both."""
    rng = np.random.default_rng(2)
    days = pd.date_range("2014-01-01", "2020-12-31")
    base = 5 + 4 * np.sin(2 * np.pi * days.dayofyear / 365)
    r = pd.Series(rng.poisson(base * 4), days, dtype=float)
    dd = pd.Series(rng.poisson(base), days, dtype=float)
    daily = pd.DataFrame({"R": r.where(days >= "2019-01-01", 0.0), "D": dd})
    cov = {"R": ("2019-01", "2020-12"), "D": ("2014-01", "2020-12")}
    monthly = DL.monthly_from_daily(daily, cov)
    s = Settings(reference="R", fill_steps=(FillStep("D", "2019-01", "2020-12", method="M1"),), min_pairs=12)
    return harmonize(monthly, s), daily


def test_window_totals_add_up():
    res, daily = _harmonized_with_daily()
    f, last = res.frame, daily.index.max()
    year = DL.window_totals(f, daily, "2020-01-01", "2020-12-31", last)
    ann = res.annual()["total"]
    assert np.allclose(year["total"], ann.loc[year.index])
    month = DL.window_totals(f, daily, "2020-03-01", "2020-03-31", last)
    assert np.allclose(month["total"], f["harmonized"][f.index.month == 3].loc[[pd.Period(f"{y}-03", "M") for y in month.index]])
    # a part of a month is the month times the share of the source satellite's detections in it
    part = DL.window_totals(f, daily, "2020-03-01", "2020-03-10", last)
    m = pd.Period("2016-03", "M")
    share = daily.loc["2016-03-01":"2016-03-10", "D"].sum() / daily.loc["2016-03-01":"2016-03-31", "D"].sum()
    assert np.isclose(part.loc[2016, "total"], f.at[m, "harmonized"] * share)
    assert part.loc[2016, "estimated"] and not part.loc[2020, "estimated"]
    assert (part["lower"] <= part["total"] + 1e-9).all() and (part["total"] <= part["upper"] + 1e-9).all()


def test_window_rules():
    res, daily = _harmonized_with_daily()
    f, last = res.frame, pd.Timestamp("2020-06-10")
    w = DL.window_totals(f, daily, "2020-06-01", "2020-06-10", last)
    assert w.index.max() == 2020 and w.index.min() == 2014
    assert DL.window_totals(f, daily, "2020-06-01", "2020-06-20", last).index.max() == 2019  # 2020 not over yet
    cross = DL.window_totals(f, daily, "2019-12-20", "2020-01-10", daily.index.max())
    assert cross.index.max() == 2020 and str(cross.loc[2015, "start"]) == "2014-12-20"  # labelled by end year
    leap = DL.window_totals(f, daily, "2020-02-01", "2020-02-29", daily.index.max())
    assert str(leap.loc[2019, "end"]) == "2019-02-28"
    with pytest.raises(ValueError):
        DL.window_totals(f, daily, "2019-01-01", "2020-06-01", last)
    c = DL.compare_window(w, 2020)
    assert c["n_years"] == len(w) and 1 <= c["rank"] <= len(w)
    assert np.isclose(c["median"], w.drop(index=2020)["total"].median())


def test_last_complete_day_drops_partial_download():
    days = pd.date_range("2026-10-20", "2026-11-11")
    s = pd.DataFrame({"NOAA20": 100.0}, index=days)
    assert DL.last_complete_day(s) == pd.Timestamp("2026-11-11")
    s.loc["2026-11-11", "NOAA20"] = 20.0  # only the first passes of the day are in
    assert DL.last_complete_day(s) == pd.Timestamp("2026-11-10")


def test_build_daily_cache_gives_the_same_tables(tmp_path):
    from burncal.daily import build_daily
    pts = tmp_path / "points"
    pts.mkdir()
    rows = pd.DataFrame({
        "latitude": [2.01, 2.02, 3.5], "longitude": [101.01, 101.02, 102.5],
        "solar_date": pd.to_datetime(["2020-01-01", "2020-01-01", "2020-01-02"]),
        "satellite": ["NOAA20", "NOAA20", "NOAA20"], "country": ["MYS"] * 3, "adm1": ["Selangor"] * 3,
        "adm2": ["Klang"] * 3,
    })
    rows.to_parquet(pts / "a.parquet", index=False)
    rows.assign(solar_date=pd.to_datetime(["2021-01-01"] * 3)).to_parquet(pts / "b.parquet", index=False)
    o1, o2 = tmp_path / "plain", tmp_path / "cached"
    o1.mkdir()
    o2.mkdir()
    a1, _ = build_daily(pts, o1, progress=False)
    build_daily(pts, o2, progress=False, cache_dir=tmp_path / "parts")
    a2, _ = build_daily(pts, o2, progress=False, cache_dir=tmp_path / "parts")  # second run: all reused
    from burncal.daily import load_daily

    def norm(path):  # as the app loads it, in a fixed row order
        t = load_daily(path)
        t["satellite"] = t["satellite"].astype(str)
        return t.sort_values(list(t.columns[:-1])).reset_index(drop=True)

    pd.testing.assert_frame_equal(norm(a1), norm(a2))
    for name in ("daily_grid.parquet",):
        g1, g2 = norm(o1 / name), norm(o2 / name)
        for c in ("country", "adm1", "adm2"):
            g1[c], g2[c] = g1[c].astype(object), g2[c].astype(object)
        pd.testing.assert_frame_equal(g1, g2)
    (pts / "b.parquet").unlink()
    a3, _ = build_daily(pts, o2, progress=False, cache_dir=tmp_path / "parts")
    assert pd.read_parquet(a3)["cell_days"].sum() == 3  # only file a is left
    assert not list((tmp_path / "parts").glob("b.*"))
