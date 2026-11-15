"""burncal.landuse: fire inside concessions and repeat burn spots (synthetic data)."""

import json

import numpy as np
import pandas as pd

from burncal.landuse import (assign_concessions, concession_change, concession_fire, load_concessions, on_peat,
                             repeat_spots)


def _geojson(tmp_path):
    sq = [[101.0, 2.0], [101.2, 2.0], [101.2, 2.2], [101.0, 2.2], [101.0, 2.0]]
    gj = {"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"name_1": "Ladang A", "name_of_gr": "Group X", "concession": "Oil palm"},
         "geometry": {"type": "Polygon", "coordinates": [sq]}}]}
    p = tmp_path / "c.geojson"
    p.write_text(json.dumps(gj))
    return p


def _fine(rows):
    """rows: (satellite, year, month, lat, lon, cd)"""
    out = pd.DataFrame(rows, columns=["satellite", "year", "month", "lat", "lon", "cd"])
    out["n"] = 1
    out["slat"] = out["lat"]
    out["slon"] = out["lon"]
    out["fy"] = np.floor(out["lat"] / 0.02).astype(int)
    out["fx"] = np.floor(out["lon"] / 0.02).astype(int)
    return out


def test_concession_shares_follow_the_harmonized_total(tmp_path):
    conc = load_concessions(_geojson(tmp_path))
    assert conc[0].name == "Ladang A" and conc[0].group == "Group X"
    assert 480 < conc[0].km2 < 500  # 0.2° x 0.2° at 2° N
    fine = _fine([
        ("NOAA20", 2020, 8, 2.1, 101.1, 3),   # inside
        ("NOAA20", 2020, 8, 2.5, 101.5, 1),   # outside
        ("SNPP", 2020, 8, 2.1, 101.1, 50),    # not the 2020 pattern satellite
    ])
    idx = assign_concessions(fine["lat"].to_numpy(), fine["lon"].to_numpy(), conc)
    assert idx.tolist() == [0, -1, 0]
    r = concession_fire(fine, idx, pd.Series({2020: 400.0}), len(conc))
    assert r["years"] == [2020]
    assert r["inside"] == [300.0]
    assert r["per"][0, 0] == 300.0


def test_concession_change_uses_noaa20_same_months():
    fine = _fine([("NOAA20", 2026, 3, 2.1, 101.1, 12), ("NOAA20", 2025, 3, 2.1, 101.1, 6),
                  ("NOAA20", 2025, 11, 2.1, 101.1, 100), ("NOAA20", 2024, 3, 2.1, 101.1, 6)])
    ch = concession_change(fine, np.zeros(4, np.int32), 1, 2026, 10, [2024, 2025])
    assert ch.loc[0, "this"] == 12 and ch.loc[0, "typical"] == 6 and ch.loc[0, "change_pct"] == 100


def test_repeat_spots_count_viirs_years_only():
    fine = _fine([
        ("Aqua", 2010, 8, 2.1, 101.1, 9),     # before 2012: ignored
        ("SNPP", 2013, 8, 2.1, 101.1, 2),
        ("NOAA20", 2013, 8, 2.1, 101.1, 2),   # NOAA-20 in 2013 is not the pattern satellite
        ("NOAA20", 2020, 8, 2.1, 101.1, 1),
        ("NOAA20", 2026, 2, 2.1, 101.1, 1),
        ("NOAA20", 2020, 8, 2.5, 101.5, 4),
    ])
    s = repeat_spots(fine, last_year=2026).sort_values("years", ascending=False)
    top = s.iloc[0]
    assert top["years"] == 3 and top["last"] == 2026 and bool(top["this_year"])
    assert top["mask"] == (1 << 1) | (1 << 8) | (1 << 14)
    assert top["cd"] == 4
    assert s.iloc[1]["years"] == 1


def test_on_peat_uses_half_mapped_cells():
    peat = pd.DataFrame({"cell_y": [210], "cell_x": [10110], "peat_share": [0.6]})
    assert on_peat(np.array([2.105, 2.5]), np.array([101.105, 101.5]), peat).tolist() == [True, False]


def test_points_outside_every_concession(tmp_path):
    conc = load_concessions(_geojson(tmp_path))
    assert assign_concessions(np.array([5.0]), np.array([110.0]), conc).tolist() == [-1]
    assert assign_concessions(np.array([]), np.array([]), conc).tolist() == []
