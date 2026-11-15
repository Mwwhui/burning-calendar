"""burncal.fine: ~2 km playback cells drawn at the detections' mean position."""

import numpy as np
import pandas as pd

from burncal.fine import choose_deg, fine_frames, fine_table, pattern_satellites


def _points():
    rows = [
        # two NOAA-20 detections in one 0.01 cell on one day = 1 cell-day, centroid between them
        (2.0011, 101.0011, "2020-03-01", "NOAA20"),
        (2.0019, 101.0019, "2020-03-01", "NOAA20"),
        # same cell, another day = a second cell-day
        (2.0015, 101.0015, "2020-03-02", "NOAA20"),
        # another fine cell
        (2.1015, 101.3015, "2020-03-02", "NOAA20"),
        # a MODIS detection in 2010
        (2.5005, 101.5005, "2010-08-05", "Aqua"),
        # an S-NPP detection in 2020: not the 2020 pattern satellite
        (2.7005, 101.7005, "2020-03-05", "SNPP"),
    ]
    return pd.DataFrame(rows, columns=["latitude", "longitude", "solar_date", "satellite"]).assign(
        solar_date=lambda d: pd.to_datetime(d["solar_date"]), adm1="Selangor", adm2=None)


def _frame():
    idx = pd.period_range("2010-01", "2020-12", freq="M")
    return pd.DataFrame({"harmonized": np.full(len(idx), 10.0)}, index=idx)


def test_pattern_satellites_follow_the_record():
    assert pattern_satellites(2005) == ("Terra", "Aqua")
    assert pattern_satellites(2015) == ("SNPP",)
    assert pattern_satellites(2024) == ("NOAA20",)


def test_fine_table_counts_cell_days_and_keeps_positions():
    f = fine_table(_points())
    n20 = f[(f["satellite"] == "NOAA20")].sort_values("cd", ascending=False)
    first = n20.iloc[0]
    assert first["cd"] == 2 and first["n"] == 3
    assert abs(first["slat"] / first["n"] - 2.0015) < 1e-9
    assert set(f["satellite"]) == {"NOAA20", "Aqua", "SNPP"}


def test_year_frames_add_up_to_the_harmonized_totals():
    out = fine_frames(_frame(), fine_table(_points()), step="year", deg=0.02)
    totals = out.groupby("period")["value"].sum()
    assert totals["2020"] == 120.0 and totals["2010"] == 120.0
    y20 = out[out["period"] == "2020"].sort_values("value")
    # 2 of 3 NOAA-20 cell-days in the first cell; S-NPP is not drawn in 2020
    assert np.allclose(y20["value"].to_numpy(), [40.0, 80.0])
    assert (out["lat"] < 2.6).all()
    # dots sit at the mean detection position, not at a cell centre
    assert abs(y20["lat"].iloc[1] - 2.0015) < 1e-9


def test_month_frames_use_noaa20_and_coarse_cells_merge():
    out = fine_frames(_frame(), fine_table(_points()), step="month", deg=0.5)
    assert set(out["period"]) == {"2020-03"}
    assert len(out) == 1 and out["value"].iloc[0] == 10.0
    assert choose_deg(fine_table(_points())) == 0.02


def test_frames_work_on_a_table_read_back_from_parquet(tmp_path):
    path = tmp_path / "f.parquet"
    fine_table(_points()).to_parquet(path, index=False)
    f = pd.read_parquet(path)
    assert set(fine_frames(_frame(), f, step="month", deg=0.02)["period"]) == {"2020-03"}
    assert set(fine_frames(_frame(), f, step="year", deg=0.02)["period"]) == {"2010", "2020"}
