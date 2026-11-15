import io

import pandas as pd

from burncal.clean import clean
from burncal.config import Settings
from burncal.io import STANDARD_COLUMNS, load_firms_folder, normalize_satellite, standardize

MODIS_CSV = """latitude,longitude,brightness,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_t31,frp,daynight,type
3.1,101.5,320.1,1.0,1.0,2015-09-01,0545,Aqua,MODIS,80,6.1,295.0,20.5,D,0
3.2,101.6,310.0,1.0,1.0,2015-09-01,0230,Terra,MODIS,25,6.1,295.0,10.0,D,0
3.3,101.7,330.0,1.0,1.0,2015-09-02,0545,Aqua,MODIS,90,6.1,295.0,30.0,D,2
"""
VIIRS_NRT_CSV = """latitude,longitude,bright_ti4,scan,track,acq_date,acq_time,satellite,instrument,confidence,version,bright_ti5,frp,daynight
2.0,111.0,340.0,0.4,0.4,2026-10-01,0512,N20,VIIRS,n,2.0NRT,290.0,5.0,D
2.1,111.1,330.0,0.4,0.4,2026-10-01,0512,N21,VIIRS,l,2.0NRT,290.0,2.0,D
"""


def test_normalize_satellite_codes():
    s = pd.Series(["A", "Aqua", "T", "N", "N20", "1", 1.0, "J2", "NOAA-21", "x"])
    out = normalize_satellite(s)
    assert out.iloc[:-1].tolist() == [
        "Aqua", "Aqua", "Terra", "SNPP", "NOAA20", "NOAA20", "NOAA20", "NOAA21", "NOAA21",
    ]
    assert pd.isna(out.iloc[-1])


def test_standardize_modis_and_viirs():
    m = standardize(pd.read_csv(io.StringIO(MODIS_CSV)), "fire_archive_M-C61_1.csv")
    v = standardize(pd.read_csv(io.StringIO(VIIRS_NRT_CSV)), "fire_nrt_J1V-C2_1.csv")
    assert list(m.columns) == STANDARD_COLUMNS
    assert set(m["satellite"]) == {"Aqua", "Terra"} and set(m["sensor"]) == {"MODIS"}
    assert (m["product"] == "SP").all()
    assert set(v["satellite"]) == {"NOAA20", "NOAA21"}
    assert (v["product"] == "NRT").all() and v["type"].isna().all()
    assert m["acq_time"].tolist() == [545, 230, 545]


def test_non_firms_table_is_rejected():
    assert standardize(pd.DataFrame({"a": [1]})) is None


def test_clean_filters(tmp_path):
    (tmp_path / "m.csv").write_text(MODIS_CSV)
    (tmp_path / "v.csv").write_text(VIIRS_NRT_CSV)
    (tmp_path / ".cache").mkdir()
    (tmp_path / ".cache" / "ignored.csv").write_text(MODIS_CSV)
    raw = load_firms_folder(tmp_path)
    assert len(raw) == 5  # .cache skipped
    out = clean(raw, Settings())
    # MODIS: conf 25 dropped, type 2 dropped -> 1 left. VIIRS: 'l' dropped, NRT (no type) kept -> 1 left
    assert len(out) == 2
    assert set(out["satellite"]) == {"Aqua", "NOAA20"}


def test_bbox_filter():
    raw = standardize(pd.read_csv(io.StringIO(MODIS_CSV)))
    out = clean(raw, Settings(bbox=(101.55, 0, 102, 10), modis_min_confidence=0, keep_type=(0, 2)))
    assert sorted(out["latitude"]) == [3.2, 3.3]


def test_nrt_dropped_where_sp_covers_dates(tmp_path):
    (tmp_path / "sp.csv").write_text(MODIS_CSV)  # SP Aqua/Terra up to 2015-09-02
    nrt = MODIS_CSV.replace(",6.1,", ",6.1NRT,").replace("3.1,101.5", "3.1001,101.5001")  # shifted copy
    nrt += "4.0,102.0,320.0,1.0,1.0,2015-09-10,0545,Aqua,MODIS,80,6.1NRT,295.0,20.0,D,0\n"
    (tmp_path / "nrt.csv").write_text(nrt)
    raw = load_firms_folder(tmp_path)
    assert len(raw) == 4  # 3 SP + only the NRT row after the SP record ends
    assert raw.loc[raw["product"] == "NRT", "acq_date"].tolist() == [pd.Timestamp("2015-09-10")]


def test_sp_preferred_over_nrt_duplicate(tmp_path):
    (tmp_path / "a_sp.csv").write_text(MODIS_CSV)
    (tmp_path / "b_nrt.csv").write_text(MODIS_CSV.replace(",6.1,", ",6.1NRT,"))
    raw = load_firms_folder(tmp_path)
    assert len(raw) == 3 and (raw["product"] == "SP").all()
