"""Cube: file-by-file processing must give the same monthly counts as the in-memory path."""

import json

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("pyarrow")
pytest.importorskip("shapely")

from burncal.aggregate import monthly_counts  # noqa: E402
from burncal.clean import clean  # noqa: E402
from burncal.config import Settings  # noqa: E402
from burncal.cube import build_cube, monthly_from_cube, platform_coverage, raw_files  # noqa: E402
from burncal.io import make_demo_data  # noqa: E402
from burncal.pipeline import run_cube  # noqa: E402
from burncal.regions import RegionTagger  # noqa: E402

FIRMS_MODIS_COLS = ["latitude", "longitude", "brightness", "scan", "track", "acq_date", "acq_time", "satellite",
                    "instrument", "confidence", "version", "bright_t31", "frp", "daynight", "type"]
FIRMS_VIIRS_COLS = ["latitude", "longitude", "bright_ti4", "scan", "track", "acq_date", "acq_time", "satellite",
                    "instrument", "confidence", "version", "bright_ti5", "frp", "daynight", "type"]
CODE = {"Terra": "Terra", "Aqua": "Aqua", "SNPP": "N", "NOAA20": "N20", "NOAA21": "N21"}


def square(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


@pytest.fixture(scope="module")
def tagger(tmp_path_factory):
    d = tmp_path_factory.mktemp("bounds")
    def write(name, feats):
        (d / name).write_text(json.dumps({"type": "FeatureCollection", "features": [
            {"type": "Feature", "properties": {"shapeName": n}, "geometry": g} for n, g in feats]}))
    # demo data spans lon 100-119, lat 1-7: split into two "countries"
    write("geoBoundaries-MYS-ADM0.geojson", [("M", square(99, 0, 110, 8))])
    write("geoBoundaries-IDN-ADM0.geojson", [("I", square(110, 0, 120, 8))])
    write("geoBoundaries-MYS-ADM1.geojson", [("West", square(99, 0, 105, 8)), ("East", square(105, 0, 110, 8))])
    return RegionTagger(d)


def write_firms_files(raw: pd.DataFrame, folder):
    """Write demo rows as FIRMS-style CSVs: one file per sensor-year, like country files."""
    for (sensor, year), g in raw.groupby(["sensor", raw["acq_date"].dt.year]):
        cols = FIRMS_MODIS_COLS if sensor == "MODIS" else FIRMS_VIIRS_COLS
        out = pd.DataFrame({c: 0 for c in cols}, index=g.index)
        for c in ("latitude", "longitude", "confidence", "frp", "daynight", "type"):
            out[c] = g[c]
        out["acq_date"] = g["acq_date"].dt.strftime("%Y-%m-%d")
        out["acq_time"] = g["acq_time"].map(lambda t: f"{int(t):04d}")
        out["satellite"] = g["satellite"].map(CODE)
        out["instrument"] = sensor
        out["version"] = "6.1" if sensor == "MODIS" else "2"
        out[cols].to_csv(folder / f"{sensor.lower()}_{year}_Test.csv", index=False)


@pytest.fixture(scope="module")
def built(tmp_path_factory, tagger):
    raw = make_demo_data(seed=3, start="2010-01", end="2021-12", scale=0.2)
    rawdir = tmp_path_factory.mktemp("raw")
    write_firms_files(raw, rawdir)
    out = tmp_path_factory.mktemp("processed")
    cube = build_cube(rawdir, out, Settings(), tagger=tagger, progress=False)
    return raw, rawdir, out, cube


def test_cube_matches_in_memory_counts(built, tagger):
    raw, _, _, cube = built
    s = Settings()
    hot = tagger.tag(clean(raw, s))
    expected = monthly_counts(hot, unit="cell_days")
    got = monthly_from_cube(cube, countries=["MYS", "IDN"])
    common = expected.columns.intersection(got.columns)
    pd.testing.assert_frame_equal(got[common].loc[expected.index], expected[common], check_freq=False)


def test_region_split_adds_up(built):
    _, _, _, cube = built
    both = monthly_from_cube(cube, countries=["MYS", "IDN"]).fillna(0)
    m = monthly_from_cube(cube, countries="MYS").fillna(0)
    i = monthly_from_cube(cube, countries="IDN").fillna(0)
    assert np.allclose(both.to_numpy(), (m + i).to_numpy())
    west = monthly_from_cube(cube, countries="MYS", adm1="West").fillna(0)
    east = monthly_from_cube(cube, countries="MYS", adm1="East").fillna(0)
    assert np.allclose(m.to_numpy(), (west + east).to_numpy())


def test_coverage_is_global_not_per_region(built):
    _, _, _, cube = built
    cov = platform_coverage(cube)
    assert cov["NOAA20"][0] == "2018-04"
    m = monthly_from_cube(cube, countries="MYS", adm1="West")
    assert m.loc[pd.Period("2018-05", "M"):, "NOAA20"].notna().all()
    assert m.loc[:pd.Period("2018-03", "M"), "NOAA20"].isna().all()


def test_incremental_rebuild_skips_processed_files(built, tagger):
    _, rawdir, out, cube = built
    manifest = json.loads((out / "manifest.json").read_text())
    assert len(manifest["files"]) == len(raw_files(rawdir))
    again = build_cube(rawdir, out, Settings(), tagger=tagger, progress=False)
    pd.testing.assert_frame_equal(again, cube)


def test_nrt_rows_covered_by_sp_are_dropped(built, tagger, tmp_path):
    _, rawdir, out, cube = built
    # an NRT copy of an SP file (shifted slightly) must not change the cube
    src = sorted(rawdir.glob("viirs_2021_*.csv"))[0]
    df = pd.read_csv(src)
    df["latitude"] += 0.0001
    df["version"] = "2.0NRT"
    df.to_csv(rawdir / "viirs_nrt_copy.csv", index=False)
    try:
        again = build_cube(rawdir, out, Settings(), tagger=tagger, progress=False)
        assert again["cell_days"].sum() == cube["cell_days"].sum()
    finally:
        (rawdir / "viirs_nrt_copy.csv").unlink()


def test_run_cube_end_to_end(built):
    _, _, _, cube = built
    res = run_cube(cube, Settings(country="MYS"))
    assert res.harmonization.series.notna().all()
    assert {"SNPP", "Aqua+Terra"} <= {s.donor for s in res.harmonization.steps if s.status == "applied"}


def test_solar_date_stub_month_is_not_coverage():
    # S-NPP files stop on 31 Dec UTC, but a few detections land on 1 Jan local solar date
    months = pd.PeriodIndex(["2025-11", "2025-12", "2026-01", "2026-01", "2026-02"], freq="M")
    cube = pd.DataFrame({
        "month": months, "satellite": ["SNPP", "SNPP", "SNPP", "NOAA20", "NOAA20"],
        "country": "MYS", "adm1": None, "adm2": None,
        "cell_days": [7000, 13000, 85, 50000, 3000], "points": [7000, 13000, 85, 50000, 3000],
        "frp_sum": 1.0,
    })
    cov = platform_coverage(cube)
    assert cov["SNPP"] == ("2025-11", "2025-12")
    assert cov["NOAA20"] == ("2026-01", "2026-02")  # a real partial month (6%) is kept
    m = monthly_from_cube(cube, countries="MYS")
    assert np.isnan(m.loc[pd.Period("2026-01", "M"), "SNPP"])
