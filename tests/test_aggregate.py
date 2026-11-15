import numpy as np
import pandas as pd

from burncal.aggregate import add_solar_date, monthly_counts


def pts(rows):
    df = pd.DataFrame(rows, columns=["latitude", "longitude", "acq_date", "acq_time", "satellite"])
    df["acq_date"] = pd.to_datetime(df["acq_date"])
    return df


def test_solar_date_moves_malaysian_night_pass_to_local_day():
    # 01:30 local at 105E (UTC+7) on 2 March = 18:30 UTC on 1 March
    df = add_solar_date(pts([(3.0, 105.0, "2020-03-01", 1830, "SNPP")]))
    assert df["solar_date"].iloc[0] == pd.Timestamp("2020-03-02")


def test_solar_date_falls_back_without_time():
    df = pts([(3.0, 105.0, "2020-03-01", np.nan, "SNPP")])
    assert add_solar_date(df)["solar_date"].iloc[0] == pd.Timestamp("2020-03-01")


def test_cell_days_count_each_cell_once_per_day_per_platform():
    rows = [
        (3.0001, 101.0001, "2020-01-05", 600, "SNPP"),
        (3.0002, 101.0002, "2020-01-05", 600, "SNPP"),   # same cell, same day -> 1
        (3.0001, 101.0001, "2020-01-06", 600, "SNPP"),   # next day -> +1
        (3.0001, 101.0001, "2020-01-05", 600, "NOAA20"),  # other platform -> own column
    ]
    m = monthly_counts(pts(rows), unit="cell_days", grid_deg=0.01)
    assert m.loc[pd.Period("2020-01", "M"), "SNPP"] == 2
    assert m.loc[pd.Period("2020-01", "M"), "NOAA20"] == 1
    p = monthly_counts(pts(rows), unit="points")
    assert p.loc[pd.Period("2020-01", "M"), "SNPP"] == 3


def test_months_outside_coverage_are_nan_inside_are_zero():
    rows = [
        (3, 101, "2020-01-05", 600, "Aqua"),
        (3, 101, "2020-04-05", 600, "Aqua"),
        (3, 101, "2020-03-05", 600, "SNPP"),
    ]
    m = monthly_counts(pts(rows))
    assert list(m.columns) == ["Aqua", "SNPP"]
    assert m.loc[pd.Period("2020-02", "M"), "Aqua"] == 0
    assert np.isnan(m.loc[pd.Period("2020-01", "M"), "SNPP"])
    assert np.isnan(m.loc[pd.Period("2020-04", "M"), "SNPP"])
    m2 = monthly_counts(pts(rows), coverage={"SNPP": ("2020-01", None)})
    assert m2.loc[pd.Period("2020-01", "M"), "SNPP"] == 0
    assert m2.loc[pd.Period("2020-04", "M"), "SNPP"] == 0


def test_monthly_index_has_no_gaps(demo_raw):
    m = monthly_counts(demo_raw.head(20000))
    idx = m.index
    assert len(idx) == (idx.max() - idx.min()).n + 1
