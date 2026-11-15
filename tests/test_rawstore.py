"""Slim raw store: Parquet copies of FIRMS CSVs must give the same table and the same cube (synthetic data)."""

import json

import pandas as pd
import pytest

pytest.importorskip("pyarrow")
pytest.importorskip("shapely")

from burncal.config import Settings  # noqa: E402
from burncal.cube import build_cube, raw_files  # noqa: E402
from burncal.io import load_firms_csv, make_demo_data  # noqa: E402
from burncal.rawstore import load_raw, migrate_manifest, slim_file, slim_path  # noqa: E402

from test_cube import tagger, write_firms_files  # noqa: E402,F401  (fixture and helper)


@pytest.fixture()
def raw_dir(tmp_path):
    d = tmp_path / "raw"
    d.mkdir()
    write_firms_files(make_demo_data(seed=3), d)
    return d


def test_slim_reads_back_identically_and_is_smaller(raw_dir):
    csv = max(raw_dir.glob("*.csv"), key=lambda p: p.stat().st_size)  # tiny files are all Parquet overhead
    std = load_firms_csv(csv)
    size = csv.stat().st_size
    out = slim_file(csv)
    assert out == slim_path(csv) and not csv.exists()
    assert out.stat().st_size < size
    pd.testing.assert_frame_equal(load_raw(out), std, check_dtype=False)


def test_not_firms_is_left_alone(tmp_path):
    p = tmp_path / "other.csv"
    p.write_text("a,b\n1,2\n")
    assert slim_file(p) is None and p.exists()


def test_cube_is_identical_from_slim_files(raw_dir, tmp_path, tagger):  # noqa: F811
    s = Settings()
    a = build_cube(raw_dir, tmp_path / "csv", s, tagger=tagger, progress=False)
    for p in sorted(raw_dir.glob("*.csv")):
        slim_file(p)
    assert all(p.suffix == ".parquet" for p in raw_files(raw_dir))
    b = build_cube(raw_dir, tmp_path / "slim", s, tagger=tagger, progress=False)
    k = ["month", "satellite", "country", "adm1", "adm2"]
    pd.testing.assert_frame_equal(a.sort_values(k).reset_index(drop=True), b.sort_values(k).reset_index(drop=True))


def test_manifest_migration_avoids_counting_twice(raw_dir, tmp_path, tagger):  # noqa: F811
    s = Settings()
    out = tmp_path / "store"
    a = build_cube(raw_dir, out, s, tagger=tagger, progress=False)
    for p in sorted(raw_dir.glob("*.csv")):
        slim_file(p)
        assert migrate_manifest(out, raw_dir, p)
    files = json.loads((out / "manifest.json").read_text())["files"]
    assert all(k.endswith(".parquet") for k in files)
    b = build_cube(raw_dir, out, s, tagger=tagger, progress=False)  # nothing new to process
    assert b["cell_days"].sum() == a["cell_days"].sum()


def test_csv_with_slim_copy_is_skipped(raw_dir):
    csv = sorted(raw_dir.glob("*.csv"))[0]
    slim_file(csv, delete_csv=False)
    files = raw_files(raw_dir)
    assert slim_path(csv) in files and csv not in files
