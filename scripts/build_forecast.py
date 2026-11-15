"""Short-range fire forecast (next 7 days, weeks 2-4) for every country, state and district.

    data/processed/forecast/latest.parquet    one row per area: forecast quantiles, usual amount,
                                              chance above usual, backtest skill, usable flag
    data/processed/forecast/history.parquet   backtest forecasts vs what happened (recent weeks)
    data/processed/forecast/summary.json      overall backtest skill, settings, issue date

See burncal.forecast for the method. Takes a few minutes.

    python scripts/build_forecast.py
    python scripts/build_forecast.py --countries MYS     # quick run
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))

import data as D  # noqa: E402
from burncal import daily as DL  # noqa: E402
from burncal import forecast as F  # noqa: E402

LEVELS = {"country": ["country"], "adm1": ["country", "adm1"], "adm2": ["country", "adm1", "adm2"]}


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "data" / "processed" / "forecast")
    ap.add_argument("--countries", nargs="*")
    ap.add_argument("--first-test-year", type=int, default=2019)
    args = ap.parse_args(argv)
    t0 = time.time()

    from burncal.daily import load_daily
    admin = load_daily(ROOT / "data" / "processed" / "daily_admin.parquet")
    last_day = pd.Timestamp(DL.last_complete_day(DL.daily_for_region(admin, None))).normalize()
    # default: the Asian countries only; Argentina has its own model (--countries ARG --out data/processed/forecast_other)
    from burncal.regions import OTHER_ISO3
    countries = sorted(args.countries or [c for c in admin["country"].dropna().unique()
                                          if c in D.COUNTRY_NAMES and c not in OTHER_ISO3])
    admin = admin[admin["country"].isin(countries)]
    try:
        from burncal.context import load_oni
        oni = load_oni()  # monthly, PeriodIndex (centre month of each 3-month season)
    except Exception:  # noqa: BLE001
        oni = None

    feats = []
    for level, keys in LEVELS.items():
        d = F.viirs_daily(admin, keys)
        if d.empty:
            continue
        wk = F.weekly(d, keys, last_day)
        # peat share of each area's fire (descriptive, all years)
        a = admin.dropna(subset=keys)
        tot = a.groupby(keys, observed=True)["cell_days"].sum()
        on = a[a["peat"]].groupby(keys, observed=True)["cell_days"].sum().reindex(tot.index, fill_value=0)
        share = (on / tot).replace([np.inf], np.nan)
        share.index = ["|".join(map(str, k if isinstance(k, tuple) else (k,))) for k in share.index]
        f = F.features(wk, keys, oni, share, None, countries)
        f["level"] = level
        for k in ("adm1", "adm2"):
            if k not in f:
                f[k] = None
        feats.append(f)
        print(f"{level}: {f['area'].nunique()} areas, {len(f):,} weeks, {time.time() - t0:,.0f} s", flush=True)
    f = pd.concat(feats, ignore_index=True)
    f["area"] = f["level"] + ":" + f["area"]

    # weather (scripts/download_weather.py): merged by area and week, kept only if it helps
    from burncal.weather import WEATHER_FEATURES, area_weekly
    wdir = ROOT / "data" / "external" / "weather"
    have_weather = (wdir / "daily.parquet").exists() and (wdir / "points.parquet").exists()
    if have_weather:
        wk_ends = pd.DatetimeIndex(sorted(f["week_end"].unique()))
        wt = area_weekly(pd.read_parquet(wdir / "daily.parquet"), pd.read_parquet(wdir / "points.parquet"), wk_ends)
        f = f.merge(wt, on=["area", "week_end"], how="left")
        print(f"weather: {f['rain_30'].notna().mean():.0%} of area-weeks have weather, {time.time() - t0:,.0f} s",
              flush=True)

    years = list(range(args.first_test_year, last_day.year + 1))
    comparison = {}
    if have_weather:
        bt0 = F.backtest(f.drop(columns=WEATHER_FEATURES), years)
        s0 = F.skill(bt0, by=None).iloc[0].to_dict()
        print(f"without weather: next week MAE {s0['h1_mae']:.4f}, weeks 2-4 {s0['h4_mae']:.4f}", flush=True)
    bt = F.backtest(f, years)
    print(f"backtest {years[0]}-{years[-1]}: {len(bt):,} forecasts, {time.time() - t0:,.0f} s", flush=True)
    per = F.skill(bt, by="area").set_index("area")
    overall = F.skill(bt, by=None).iloc[0].to_dict()
    use_weather = have_weather
    if have_weather:
        print(f"with weather:    next week MAE {overall['h1_mae']:.4f}, weeks 2-4 {overall['h4_mae']:.4f}", flush=True)
        comparison = {"without_weather": {k: v for k, v in s0.items() if k != "area"},
                      "with_weather": {k: v for k, v in overall.items() if k != "area"}}
        # keep weather only if it lowers the error of the next-week forecast
        use_weather = overall["h1_mae"] < s0["h1_mae"]
        if not use_weather:
            f = f.drop(columns=WEATHER_FEATURES)
            bt, overall = bt0, s0
            per = F.skill(bt, by="area").set_index("area")

    final = F.fit(f)  # every week whose targets are known
    latest = f[f["week_end"] == last_day].copy()
    p = F.predict(final, latest).join(F.baselines(latest))
    latest = latest.join(p)
    rows = []
    for _, r in latest.iterrows():
        s = per.loc[r["area"]] if r["area"] in per.index else pd.Series(dtype=float)
        row = {"area": r["area"], "level": r["level"], "country": r["country"], "adm1": r["adm1"], "adm2": r["adm2"],
               "issued": last_day.date().isoformat()}
        for h in F.HORIZONS:
            usual = float(r[f"{h}_clim"]) if pd.notna(r[f"{h}_clim"]) else np.nan
            q10, q50, q90 = (float(r[f"{h}_q{q}"]) for q in (10, 50, 90))
            row.update({f"{h}_q10": q10, f"{h}_q50": q50, f"{h}_q90": q90, f"{h}_usual": usual,
                        f"{h}_p_above": F.p_above(q10, q50, q90, usual) if np.isfinite(usual) else np.nan,
                        f"{h}_skill_persist": s.get(f"{h}_skill_persist", np.nan),
                        f"{h}_skill_clim": s.get(f"{h}_skill_clim", np.nan),
                        f"{h}_coverage": s.get(f"{h}_coverage", np.nan), f"{h}_hit": s.get(f"{h}_hit", np.nan),
                        f"{h}_n": s.get(f"{h}_n", np.nan)})
            row[f"{h}_usable"] = bool(np.nan_to_num(row[f"{h}_skill_persist"]) > F.SKILL_MIN
                                      and np.nan_to_num(row[f"{h}_skill_clim"]) > F.SKILL_MIN)
        row["recent_y"] = float(np.expm1(r["lag1"]))
        # the weather behind the forecast (shown in the app)
        for c in ("rain_30", "rain_30_anom", "dry_days", "soil", "soil_anom", "tmax_7"):
            row[f"w_{c}"] = float(r[c]) if c in r.index and pd.notna(r[c]) else np.nan
        rows.append(row)
    out = args.out
    out.mkdir(parents=True, exist_ok=True)
    pd.DataFrame(rows).to_parquet(out / "latest.parquet", index=False)
    keep = bt[bt["week_end"] > last_day - pd.Timedelta(weeks=60)]
    keep.to_parquet(out / "history.parquet", index=False)
    usable = pd.DataFrame(rows)
    summary = {
        "issued": last_day.date().isoformat(), "test_years": years, "quantiles": list(F.QUANTILES),
        "skill_min": F.SKILL_MIN, "areas": len(rows),
        "usable_h1": int(usable["h1_usable"].sum()), "usable_h4": int(usable["h4_usable"].sum()),
        "overall": {k: (None if isinstance(v, float) and not np.isfinite(v) else v) for k, v in overall.items()},
        "features": F.feature_names(f),
        "weather_used": bool(use_weather),
        "weather_comparison": comparison,
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=str), encoding="utf-8")
    print(json.dumps(summary["overall"], indent=1, default=str))
    print(f"usable: next week {summary['usable_h1']}/{len(rows)}, weeks 2-4 {summary['usable_h4']}/{len(rows)}; "
          f"{time.time() - t0:,.0f} s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
