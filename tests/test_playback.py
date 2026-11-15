"""Playback map frames (synthetic data only)."""

import numpy as np
import pandas as pd

from burncal.playback import cell_frames, display_deg


def _frame_and_grid():
    months = pd.period_range("2016-01", "2019-12", freq="M")
    frame = pd.DataFrame({"harmonized": 100.0, "source": np.where(months.year < 2018, "SNPP converted (M1)",
                                                                   "NOAA20 measured")}, index=months)
    rows = []
    for m in months:
        d = m.start_time
        # SNPP sees cell A 3x more than cell B; NOAA20 sees them equally; Aqua (not a source) only in C
        rows += [(d, "SNPP", 10, 1010, 3), (d, "SNPP", 11, 1010, 1), (d, "NOAA20", 10, 1010, 5),
                 (d, "NOAA20", 11, 1010, 5), (d, "Aqua", 30, 1030, 50)]
    grid = pd.DataFrame(rows, columns=["date", "satellite", "gy", "gx", "cell_days"])
    return frame, grid


def test_frames_add_up_and_use_the_source_satellite():
    frame, grid = _frame_and_grid()
    f = cell_frames(frame, grid, step="year", deg=0.1, last_day="2019-12-31")
    by_year = f.groupby("period")["value"].sum()
    assert np.allclose(by_year.to_numpy(), 1200.0)  # 12 months x 100
    y16 = f[f["period"] == "2016"].assign(lat=lambda x: x["lat"].round(2)).set_index("lat")["value"]
    assert np.isclose(y16.loc[1.05], 900) and np.isclose(y16.loc[1.15], 300)  # SNPP pattern 3:1
    y19 = f[f["period"] == "2019"].assign(lat=lambda x: x["lat"].round(2)).set_index("lat")["value"]
    assert np.isclose(y19.loc[1.05], 600) and np.isclose(y19.loc[1.15], 600)
    assert not (f["lat"] > 2).any()  # Aqua-only cell never drawn: Aqua is not a source here
    assert f.attrs["partial"] is None and list(f.attrs["totals"].index) == ["2016", "2017", "2018", "2019"]


def test_monthly_frames_and_coarse_grid():
    frame, grid = _frame_and_grid()
    f = cell_frames(frame, grid, step="month", deg=0.5, last_day="2019-12-15")
    assert f["period"].nunique() == 48 and f.attrs["partial"] == "2019-12"
    assert (f.groupby("period").size() == 1).all()  # both cells fall in one 0.5 deg square
    assert display_deg(5_000) == 0.1 and display_deg(1_000_000) == 1.0
