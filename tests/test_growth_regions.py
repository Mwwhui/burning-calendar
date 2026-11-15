"""scripts/build_growth.py: Asia and Americas events are fitted apart (synthetic data)."""

import importlib.util
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("build_growth", ROOT / "scripts" / "build_growth.py")
bg = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bg)


def test_region_split_by_longitude():
    ev = pd.DataFrame({"lon": [101.5, -60.2, 30.0, -57.9], "country": ["MYS", "ARG", "COD", "BRA"]})
    assert bg.region_rows(ev, "asia").tolist() == [True, False, True, False]
    assert bg.region_rows(ev, "americas").tolist() == [False, True, False, True]
