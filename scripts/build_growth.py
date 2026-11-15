"""Fire-growth model: backtest, then scores for fires that are burning now.

    data/processed/growth/summary.json   backtest scores per target (model vs day-3 area rule), usable flags
    data/processed/growth/scores.parquet event_id, p_big, p_long for events that started in the last 30 days

See burncal.growth for the method.

    python scripts/build_growth.py                                                  # Asia boxes
    python scripts/build_growth.py --region americas --out data/processed/growth_other   # Argentina box

Asia and the Americas (Argentina's download box) get separate models, so adding Argentina never changes an
Asian score. The split is by longitude (AMERICAS_LON), because each download box also catches fires in
neighbouring countries and those were always part of the Asian training set.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from burncal import growth as G  # noqa: E402
from burncal.events import load_events  # noqa: E402

AMERICAS_LON = -30.0  # events west of this belong to the Argentina box; everything else to the Asia boxes


def region_rows(ev: pd.DataFrame, region: str) -> pd.Series:
    west = ev["lon"] < AMERICAS_LON
    return west if region == "americas" else ~west


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--events", type=Path, default=ROOT / "data" / "processed" / "events.parquet")
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed" / "growth")
    ap.add_argument("--first-test-year", type=int, default=2021)
    ap.add_argument("--region", choices=["asia", "americas"], default="asia")
    args = ap.parse_args(argv)
    t0 = time.time()
    ev = load_events(args.events)
    ev = ev[region_rows(ev, args.region).to_numpy()].reset_index(drop=True)
    if "early_cells" not in ev:
        sys.exit("events.parquet has no early_* columns: rebuild it with scripts/build_events.py")
    try:
        from burncal.context import load_oni
        oni = load_oni()
    except Exception:  # noqa: BLE001
        oni = None
    f = G.features(ev, oni)
    last = ev["end"].max()
    years = list(range(args.first_test_year, last.year + 1))
    # the newest events may still grow: only test on events that ended >= 10 days before the data ends
    settled = ev["end"] < last - pd.Timedelta(days=10)
    bt = G.backtest(f[settled.to_numpy()], years)
    sc = G.scores(bt)
    summary = {"events": len(ev), "test_years": years, "big_km2": G.BIG_KM2, "long_days": G.LONG_DAYS,
               "issued_after_days": 3, "targets": {}}
    for _, r in sc.iterrows():
        d = {k: (float(v) if not isinstance(v, str) else v) for k, v in r.items()}
        # useful = clearly better than ranking by day-3 area: >= 20 % higher average precision
        d["usable"] = bool(r["p_ap"] >= 1.2 * r["baseline_ap"] and r["p_auc"] > r["baseline_auc"])
        summary["targets"][r["target"]] = d
    print(sc.round(3).T.to_string())
    models = G.fit_all(f[settled.to_numpy()])
    recent = ev["start"] >= last - pd.Timedelta(days=30)
    p = G.predict(models, f[recent.to_numpy()])
    out = pd.DataFrame({"event_id": ev.loc[recent, "event_id"].to_numpy(), "p_big": p["p_big"].to_numpy(),
                        "p_long": p["p_long"].to_numpy()})
    args.out.mkdir(parents=True, exist_ok=True)
    out.to_parquet(args.out / "scores.parquet", index=False)
    (args.out / "summary.json").write_text(json.dumps(summary, indent=1), encoding="utf-8")
    print(f"scored {len(out):,} recent events; usable: "
          + ", ".join(f"{k}={v['usable']}" for k, v in summary["targets"].items()) + f"; {time.time() - t0:,.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
