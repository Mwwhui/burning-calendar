"""Data access used by the web export (app/data.py): demo results, region options, points, notes."""

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app"))

import data as D  # noqa: E402


def test_data_helpers_demo():
    res = D.compute(None, None, None, None)
    nums = D.summary_numbers(res)
    assert 1 <= nums["peak_month"] <= 12 and nums["rank"] >= 1
    frames = D.calendar_frames(res)
    assert frames["value"].shape[1] == 12 and frames["estimated"].dtypes.eq(bool).all()
    cum = D.cumulative_by_year(res.harmonization.series)
    assert (cum.diff().dropna(how="all").fillna(0) >= -1e-9).all().all()  # cumulative never decreases


def test_region_options_and_points(tmp_path):
    cube = pd.DataFrame({
        "month": pd.PeriodIndex(["2020-01"] * 4, freq="M"),
        "satellite": ["NOAA20"] * 4,
        "country": ["MYS", "MYS", "IDN", "PNG"],
        "adm1": ["Sarawak", "Sabah", "Riau", None],
        "adm2": ["Miri", None, None, None],
        "cell_days": [5, 9, 20, 3], "points": [5, 9, 20, 3], "frp_sum": [1.0] * 4,
    })
    opts = D.region_options(cube)
    assert list(opts) == ["IDN", "MYS"]  # sorted by name; PNG (not Asia) excluded
    assert list(opts["MYS"]) == ["Sabah", "Sarawak"]  # by activity
    assert opts["MYS"]["Sarawak"] == ["Miri"]

    # points from two files with different null patterns combine through the fixed schema
    pdir = tmp_path / "points"
    pdir.mkdir()
    base = dict(latitude=1.0, longitude=110.0, acq_date=pd.Timestamp("2020-01-05"), acq_time=600.0,
                solar_date=pd.Timestamp("2020-01-05"), satellite="NOAA20", sensor="VIIRS", product="SP",
                confidence="n", frp=1.0, daynight="D", type=0.0)
    pd.DataFrame([{**base, "country": "MYS", "adm1": "Sarawak", "adm2": "Miri"}]).to_parquet(pdir / "a.parquet")
    pd.DataFrame([{**base, "country": "IDN", "adm1": "Riau", "adm2": None}]).to_parquet(pdir / "b.parquet")
    pts, cut = D.read_points("MYS", "Sarawak", None, "2020-01-01", "2020-01-31", points_dir=pdir)
    assert len(pts) == 1 and not cut
    pts, _ = D.read_points(None, None, None, "2020-01-01", "2020-01-31", points_dir=pdir)
    assert len(pts) == 2
    pts, cut = D.read_points(None, None, None, "2020-01-01", "2020-01-31", limit=1, points_dir=pdir)
    assert len(pts) == 1 and cut


def test_running_month_left_out_of_season_to_date():
    res = D.compute(None, None, None, None)  # demo series ends Dec 2025
    last = res.harmonization.series.dropna().index.max()
    done = D.summary_numbers(res, today=pd.Timestamp("2030-01-01"))
    running = D.summary_numbers(res, today=last.to_timestamp() + pd.Timedelta(days=10))
    assert done["partial_month"] is None and running["partial_month"] == str(last)
    assert running["through_month"] == (last - 1).month
    fr = D.calendar_frames(res, today=last.to_timestamp())
    assert fr["partial"].to_numpy().sum() == 1 and bool(fr["partial"].loc[last.year, last.month])
    assert isinstance(done["busiest_year_estimated"], bool)
    assert all(isinstance(y, int) and y != done["busiest_year"] for y in done["busiest_ties"])


def test_too_few_fires_note():
    """Tiny area: older satellites not converted; the note names the first month of the record."""
    from burncal.config import Settings
    from burncal.io import make_demo_data
    from burncal.pipeline import run
    res = run(make_demo_data(), Settings(min_fire_pairs=10 ** 6))  # every conversion refused
    first = D.too_few_fires(res)
    assert first is not None and pd.Period(first) == res.harmonization.series.dropna().index.min()
    assert D.too_few_fires(D.compute(None, None, None, None)) is None
