"""Static-source mask and peat split (synthetic data only)."""

import numpy as np
import pandas as pd
import pytest

from burncal import daily as DL
from burncal.config import Settings
from burncal.peat import on_peat
from burncal.static import drop_static, label_counts, mask_id, static_cells


def _labelled():
    # a flare at (1.005, 101.005) labelled type 2 four times; one stray label elsewhere; fires type 0
    return pd.DataFrame({
        "latitude": [1.005] * 4 + [1.5, 1.2, 1.2],
        "longitude": [101.005] * 4 + [101.5, 101.2, 101.2],
        "acq_date": ["2019-01-01", "2019-05-01", "2020-03-01", "2021-01-01", "2020-01-01", "2020-01-01", "2020-01-02"],
        "type": [2, 2, 2, 2, 2, 0, 0],
    })


def test_mask_needs_repeated_labels():
    counts = label_counts([_labelled(), pd.DataFrame({"latitude": [1.0], "longitude": [1.0], "acq_date": ["2020-01-01"],
                                                      "type": [np.nan]})])
    assert len(counts) == 2  # only cells with a static label; unlabelled rows ignored
    flare = counts[counts["cell_y"] == 100].iloc[0]
    assert (flare["n_static"], flare["first_year"], flare["last_year"]) == (4, 2019, 2021)
    mask = static_cells(counts, min_labels=3)
    assert len(mask) == 1 and mask_id(mask) != mask_id(static_cells(counts, 1))


def test_drop_static_removes_every_satellite_in_the_cell():
    mask = static_cells(label_counts([_labelled()]), 3)
    nrt = pd.DataFrame({"latitude": [1.001, 1.009, 1.011, 1.2], "longitude": [101.009, 101.001, 101.005, 101.2],
                        "satellite": ["NOAA20", "Aqua", "NOAA20", "NOAA20"]})
    kept = drop_static(nrt, mask)
    assert list(kept.index) == [2, 3]  # both points in the flare cell go; the next cell north stays
    assert drop_static(nrt, None) is nrt


def test_cube_build_applies_mask(tmp_path):
    from burncal.cube import build_cube

    raw = tmp_path / "raw"
    raw.mkdir()
    rows = pd.DataFrame({"latitude": [1.005, 1.2], "longitude": [101.005, 101.2], "bright_ti4": 330.0, "scan": 0.4,
                         "track": 0.4, "acq_date": "2026-09-01", "acq_time": "0600", "satellite": "N20",
                         "instrument": "VIIRS", "confidence": "n", "version": "2.0NRT", "bright_ti5": 290.0,
                         "frp": 5.0, "daynight": "D"})
    rows.to_csv(raw / "VIIRS_NOAA20_NRT_2026.csv", index=False)
    mpath = tmp_path / "mask.parquet"
    static_cells(label_counts([_labelled()]), 3).to_parquet(mpath)

    class NoTag:
        def tag(self, d):
            return d.assign(country="MYS", adm1="A", adm2=None)

    cube = build_cube(raw, tmp_path / "out", Settings(static_mask=str(mpath)), tagger=NoTag(), progress=False)
    assert cube["cell_days"].sum() == 1
    with pytest.raises(ValueError):  # same folder, other settings
        build_cube(raw, tmp_path / "out", Settings(), tagger=NoTag(), progress=False)


def test_peat_split_adds_up():
    cells = pd.DataFrame({"cell_y": [100, 101], "cell_x": [10100, 10100], "peat_share": [0.8, 0.3]})
    assert list(on_peat([1.005, 1.015, 1.5], [101.005, 101.005, 101.0], cells)) == [True, False, False]
    pts = pd.DataFrame({"latitude": [1.005, 1.015, 1.5], "longitude": [101.005, 101.005, 101.0],
                        "solar_date": pd.to_datetime(["2020-01-01"] * 3), "satellite": "NOAA20",
                        "country": "MYS", "adm1": "A", "adm2": None})
    admin, grid = DL.daily_tables(pts, peat_cells=cells)
    admin = admin.assign(date=pd.to_datetime(admin["date"]))
    for c in DL.REGION_COLS:
        admin[c] = admin[c].replace("", None)
    tot = DL.daily_for_region(admin, "MYS")["NOAA20"].sum()
    on = DL.daily_for_region(admin, "MYS", peat=True)["NOAA20"].sum()
    off = DL.daily_for_region(admin, "MYS", peat=False)["NOAA20"].sum()
    assert (tot, on, off) == (3, 1, 2)
    assert grid.groupby("peat")["cell_days"].sum().to_dict() == {False: 2, True: 1}


def test_peat_cells_from_tif(tmp_path):
    rasterio = pytest.importorskip("rasterio")
    from rasterio.transform import from_origin

    from burncal.peat import peat_cells_from_tif

    a = np.zeros((20, 20), "uint8")
    a[:10, :10] = 1  # north-west quarter is peat; one no-data pixel
    a[19, 19] = 16
    p = tmp_path / "peat.tif"
    with rasterio.open(p, "w", driver="GTiff", width=20, height=20, count=1, dtype="uint8", crs="EPSG:4326",
                       transform=from_origin(101.0, 1.02, 0.001, 0.001), nodata=16) as w:
        w.write(a, 1)
    c = peat_cells_from_tif(p, box=(101.0, 1.0, 101.02, 1.02))
    top_left = c[(c["cell_y"] == 101) & (c["cell_x"] == 10100)]
    assert len(c) == 1 and float(top_left["peat_share"].iloc[0]) == 1.0


def test_burned_area_comparison_and_seam():
    from burncal.burned_area import compare_burned_area, seam_steps

    idx = pd.period_range("2003-01", "2020-12", freq="M")
    rng = np.random.default_rng(1)
    ba = pd.Series(np.exp(rng.normal(5, 1, len(idx))), idx)
    gfed = pd.DataFrame({"total": ba, "peat": ba * 0.1})
    good = ba * 3 * np.exp(rng.normal(0, 0.1, len(idx)))
    c = compare_burned_area(good, gfed)
    assert c["r_monthly"] > 0.95 and c["same_top3"] and c["months"] == len(idx)
    assert abs(seam_steps(good, gfed)["step_2012"]) < 0.1
    jumpy = good.where(idx.year < 2012, good * 3)  # a raw join: 3x more from 2012
    assert abs(seam_steps(jumpy, gfed)["step_2012"] - 2.0) < 0.2


def test_bigger_mask_on_existing_store_equals_rebuild(tmp_path):
    from burncal.cube import apply_mask_to_store, build_cube

    raw = tmp_path / "raw"
    raw.mkdir()
    pts = pd.DataFrame({"latitude": [1.005, 1.505, 1.2], "longitude": [101.005, 101.505, 101.2], "bright_ti4": 330.0,
                        "scan": 0.4, "track": 0.4, "acq_date": "2026-09-01", "acq_time": "0600", "satellite": "N20",
                        "instrument": "VIIRS", "confidence": "n", "version": "2.0NRT", "bright_ti5": 290.0,
                        "frp": 5.0, "daynight": "D"})
    pts.to_csv(raw / "VIIRS_NOAA20_NRT_2026.csv", index=False)
    counts = label_counts([_labelled()])  # flare cell: 4 labels; cell at (1.5, 101.5): 1 label
    small, big = tmp_path / "k3.parquet", tmp_path / "k1.parquet"
    static_cells(counts, 3).to_parquet(small)
    static_cells(counts, 1).to_parquet(big)

    class NoTag:
        def tag(self, d):
            return d.assign(country="MYS", adm1="A", adm2=None)

    build_cube(raw, tmp_path / "a", Settings(static_mask=str(small)), tagger=NoTag(), progress=False)
    after = apply_mask_to_store(tmp_path / "a", big, progress=False)
    fresh = build_cube(raw, tmp_path / "b", Settings(static_mask=str(big)), tagger=NoTag(), progress=False)
    assert after["cell_days"].sum() == fresh["cell_days"].sum() == 1
    # the store now carries the new mask: an incremental build with it is accepted
    build_cube(raw, tmp_path / "a", Settings(static_mask=str(big)), tagger=NoTag(), progress=False)
