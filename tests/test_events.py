"""Fire events: grouping rule and comparison with past events (synthetic data only)."""

import numpy as np
import pandas as pd

from burncal.events import active_events, compare_event, find_events


def _pts(rows):
    d = pd.DataFrame(rows, columns=["latitude", "longitude", "solar_date", "frp"])
    d["solar_date"] = pd.to_datetime(d["solar_date"])
    return d.assign(country="MYS", adm1="Sarawak", adm2=None)


def test_touching_cells_within_gap_join():
    ev = find_events(_pts([
        (1.005, 101.005, "2020-01-01", 5.0),
        (1.015, 101.015, "2020-01-04", 9.0),  # diagonal neighbour, 3 days later -> same fire
        (1.015, 101.015, "2020-01-12", 2.0),  # same cell 8 days later -> new fire (gap > 5)
        (1.035, 101.005, "2020-01-02", 1.0),  # two cells away -> separate
        (1.005, 101.005, "2020-01-01", 7.0),  # second point, same cell-day
    ]))
    assert len(ev) == 3
    first = ev.iloc[0]
    assert (first["cell_days"], first["cells"], first["days"], first["frp_max"]) == (2, 2, 4, 9.0)
    assert first["start"] == pd.Timestamp("2020-01-01") and first["end"] == pd.Timestamp("2020-01-04")
    assert abs(first["area_km2"] - 2 * 1.1132 ** 2 * np.cos(np.radians(1.01))) < 0.01
    assert first["country"] == "MYS"


def test_chain_links_through_intermediate_cells():
    # a line of cells burning one after another over 20 days is one moving fire
    rows = [(1.005 + 0.01 * i, 101.005, f"2020-02-{1 + 2 * i:02d}", 1.0) for i in range(10)]
    ev = find_events(_pts(rows))
    assert len(ev) == 1 and ev.iloc[0]["days"] == 19 and ev.iloc[0]["cells"] == 10


def test_compare_and_active():
    rows = [(1.005, 101.005 + 0.01 * i, "2019-03-01", 1.0) for i in range(5)]  # 5 cells
    rows += [(2.005, 101.005, "2020-03-01", 1.0)]  # 1 cell
    rows += [(3.005, 101.005 + 0.01 * i, "2021-03-01", 1.0) for i in range(3)]  # current, 3 cells
    ev = find_events(_pts(rows))
    cur = ev.sort_values("start").iloc[-1]
    c = compare_event(cur, ev)
    assert c["n"] == 2 and c["share_smaller"] == 0.5 and c["rank"] == 2
    assert c["bigger_before"]["start"] == pd.Timestamp("2019-03-01")
    assert list(active_events(ev, "2021-03-03")["start"]) == [pd.Timestamp("2021-03-01")]


def test_early_columns_only_see_the_first_three_days():
    from burncal.events import find_events
    # one fire: 1 cell on day 0, a neighbour on day 2, then 3 more cells on day 6 (within the 5-day gap)
    rows = [(2.0005, 101.0005, "2020-03-01", 5.0), (2.0005, 101.0105, "2020-03-03", 7.0)]
    rows += [(2.0005, 101.0205 + 0.01 * k, "2020-03-07", 50.0) for k in range(3)]
    pts = pd.DataFrame(rows, columns=["latitude", "longitude", "solar_date", "frp"])
    pts["solar_date"] = pd.to_datetime(pts["solar_date"])
    ev = find_events(pts)
    assert len(ev) == 1
    e = ev.iloc[0]
    assert e["cells"] == 5 and e["early_cells"] == 2
    assert e["early_days"] == 2 and e["early_frp_max"] == 7.0 and e["early_frp_sum"] == 12.0
    assert e["early_area_km2"] < e["area_km2"]


def test_event_cell_days_finds_each_event_again():
    from burncal.events import cell_days, dots_json, event_cell_days
    rows = [(1.005 + 0.01 * i, 101.005, f"2020-02-{1 + 2 * i:02d}", float(i)) for i in range(6)]  # moving fire
    rows += [(1.005, 101.025, "2020-02-20", 3.0)]  # inside the box of the fire, but 9 days after -> its own event
    rows += [(1.065, 101.005, "2020-02-12", 4.0)]  # touches the fire's last cell on its last day
    pts = _pts(rows)
    ev = find_events(pts)
    cd = cell_days(pts)
    for _, e in ev.iterrows():
        got = event_cell_days(cd, e)
        assert len(got) == e["cell_days"]
        assert got["day"].min() == (e["start"] - pd.Timestamp("2000-01-01")).days
    big = ev.loc[ev["cell_days"].idxmax()]
    j = dots_json(event_cell_days(cd, big), big["event_id"], big["start"])
    assert j["d"][0] == 0 and j["gy"] == sorted(j["gy"]) and len(j["frp"]) == big["cell_days"] == 7
    assert abs((j["gy0"] + j["gy"][-1] + 0.5) * j["grid"] - 1.065) < 1e-9


def test_event_cell_days_empty_when_table_is_stale():
    from burncal.events import cell_days, event_cell_days
    pts = _pts([(1.005, 101.005, "2020-01-01", 1.0)])
    e = find_events(pts).iloc[0].copy()
    e["cell_days"] = 5
    assert event_cell_days(cell_days(pts), e).empty


def test_load_events_reads_columns_and_compacts(tmp_path):
    from burncal.events import load_events
    p = tmp_path / "ev.parquet"
    pd.DataFrame({"event_id": [1, 2], "start": ["2020-01-01", "2020-02-01"], "end": ["2020-01-03", "2020-02-02"],
                  "country": ["ARG", "MYS"], "adm1": ["Entre Ríos", None], "adm2": [None, None],
                  "area_km2": [3.0, 1.0], "early_cells": [1, 1]}).to_parquet(p)
    ev = load_events(p, columns=["event_id", "start", "end", "country", "adm1", "adm2", "area_km2"], compact=True)
    assert "early_cells" not in ev and ev["start"].dtype.kind == "M"
    assert str(ev["country"].dtype) == "category"
    assert (ev["adm1"] == "Entre Ríos").tolist() == [True, False] and ev["adm1"].isna().tolist() == [False, True]
