"""Backcast test: how well does each MODIS -> VIIRS conversion extrapolate backwards in time?

    python scripts/backcast_check.py [--cube data/processed/cube.parquet]

The MODIS conversions are fitted on 2012-2020 and applied to 2002-2011, i.e. backwards
in time. Leave-one-year-out inside the fit window cannot tell how well that works. Here
each conversion is fitted on late years only and must predict earlier years where S-NPP
was measured: fit 2017-2020 -> predict 2012-2015, and fit 2016-2020 -> predict 2012-2014.

Prints monthly RMSE(log1p) per region and averaged over regions, for each single route
(Aqua or Terra, methods M1-M3) and for every log-mean combination of the two routes.
The chain's "Aqua+Terra" step (config.DEFAULT_FILL_STEPS) uses the winner.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from burncal.cube import load_cube, monthly_from_cube  # noqa: E402
from burncal.harmonize import METHODS, make_pairs  # noqa: E402

REGIONS = [("SEA", None), ("MYS", "MYS"), ("IDN", "IDN"), ("MMR", "MMR"), ("THA", "THA"),
           ("KHM", "KHM"), ("LAO", "LAO"), ("VNM", "VNM"), ("PHL", "PHL")]
SPLITS = [(("2017-01", "2020-12"), ("2012-02", "2015-12")), (("2016-01", "2020-12"), ("2012-02", "2014-12"))]
SINGLE = ["M1", "M2", "M3"]


def backcast_table(monthly: pd.DataFrame, fit, test, target: str = "SNPP") -> dict[str, float]:
    """Monthly RMSE(log1p) on the test window for single routes and their log-mean combinations."""
    idx = make_pairs(monthly["Aqua"], monthly[target], *test).index.intersection(
        make_pairs(monthly["Terra"], monthly[target], *test).index)
    obs = np.log1p(monthly[target][idx].to_numpy(float))
    mon = idx.month.to_numpy()
    lp = {}
    for donor in ("Aqua", "Terra"):
        for m in SINGLE:
            f = METHODS[m](make_pairs(monthly[donor], monthly[target], *fit))
            lp[(donor, m)] = np.log1p(f(monthly[donor][idx].to_numpy(float), mon))
    rmse = lambda v: float(np.sqrt(np.mean((v - obs) ** 2)))  # noqa: E731
    out = {f"{d} {m}": rmse(v) for (d, m), v in lp.items()}
    for a in SINGLE:
        for b in SINGLE:
            out[f"Aqua {a} + Terra {b}"] = rmse((lp[("Aqua", a)] + lp[("Terra", b)]) / 2)
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--cube", type=Path, default=Path("data/processed/cube.parquet"))
    args = ap.parse_args(argv)
    cube = load_cube(args.cube)
    rows = []
    for fit, test in SPLITS:
        for name, country in REGIONS:
            r = backcast_table(monthly_from_cube(cube, countries=country), fit, test)
            rows.append({"split": f"fit {fit[0][:4]}-{fit[1][:4]} -> {test[0][:4]}-{test[1][:4]}", "region": name, **r})
    t = pd.DataFrame(rows)
    summary = t.drop(columns="region").groupby("split").mean().T
    summary = summary.sort_values(summary.columns[0])
    print("Monthly backcast RMSE(log1p), mean over regions (lower = better)")
    print(summary.round(3).to_string())
    best = summary.index[0]
    print(f"\nBest: {best}")
    print("\nPer region (first split):")
    first = t[t["split"] == t["split"].iloc[0]].set_index("region")
    print(first[["Aqua M3", "Terra M2", best]].round(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
