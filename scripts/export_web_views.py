"""Blocks for the web app's detail views (used by scripts/export_web.py).

Every function turns the output of the package / app/data.py functions into plain JSON-safe
dicts. Nothing here computes new results.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

import data as D  # app/data.py (export_web.py puts app/ on the path)
from burncal import daily as DL


def num(x, nd: int = 1):
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    return round(x, nd) if math.isfinite(x) else None


def _str(x) -> str | None:
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return None
    if isinstance(x, pd.Period):
        return str(x)
    if isinstance(x, (pd.Timestamp, np.datetime64)):
        return str(pd.Timestamp(x).date())
    return str(x)


# ----------------------------------------------------------------------------- method
def raw_block(res) -> dict:
    """What each satellite saw, monthly (not converted)."""
    m = res.monthly
    return {"months": [str(p) for p in m.index],
            "sats": list(m.columns),
            "values": {c: [num(v, 0) for v in m[c]] for c in m.columns}}


def steps_block(res) -> list[dict]:
    out = []
    for s in res.harmonization.steps:
        loyo = None
        if s.loyo is not None and len(s.loyo):
            t = s.loyo.reset_index()
            loyo = [{"method": str(r.get("method", r.get("index"))), "route": _str(r.get("route")),
                     "rmse": num(r.get("RMSE_log_mean"), 3), "bias": num(r.get("bias_pct_mean"), 1),
                     "years": int(r["years"]) if pd.notna(r.get("years")) else None} for _, r in t.iterrows()]
        out.append({
            "donor": s.donor, "status": s.status, "method": s.method or None,
            "fitWindow": [_str(x) for x in s.fit_window] if s.fit_window else None,
            "monthsFilled": int(s.months_filled or 0),
            "drift": num(s.drift.get("slope_log_per_year"), 3) if s.drift else None,
            "why": s.selection or s.reason or None, "loyo": loyo,
        })
    return out


def seams_block(res) -> dict:
    rows = [{"seam": str(r["seam"]), "stepPct": num(r["step_pct"]), "placebo": num(r["placebo_pct"], 2),
             "nPlacebo": int(r["n_placebo"])} for _, r in res.seams.iterrows()]
    naive = res.naive_seams
    return {"rows": rows, "naiveStep2012": num(naive["step_pct"].iloc[0]) if len(naive) else None}


def sat_diff_block(country, adm1) -> dict | None:
    d = D.satellite_differences(country, adm1)
    if d is None:
        return None
    t = d["table"]
    return {"years": list(d["years"]),
            "rows": [{"sat": i, "detections": int(r["detections"]), "vsNoaa20": num(r["vs_noaa20"], 3),
                      "night": num(r["night_share"], 3), "weak": num(r["weak_share"], 3)}
                     for i, r in t.iterrows()]}


# ----------------------------------------------------------------------------- outlook
def outlook_block(res) -> dict | None:
    o = D.season_outlook(res)
    if o is None:
        return None
    sk = o["skill"]
    out = {
        "months": [int(m) for m in o["months"]], "share": num(o["share"], 3),
        "seasonStart": _str(o["season_start"]), "oni": num(o["oni"], 2), "oniMonth": _str(o["oni_month"]),
        "lead": int(o["lead"]), "usefulLeads": [int(x) for x in o.get("useful_leads", [])],
        "pastExtremes": int(o.get("past_extremes", 0)),
        "skill": {"useful": bool(sk.get("useful")), "n": int(sk.get("n", 0)), "hits": int(sk.get("hits", 0)),
                  "r": num(sk.get("r"), 2), "msss": num(sk.get("msss"), 3)},
    }
    if sk.get("useful"):
        out.update({k: num(o[k], 3 if k.startswith("p_") else 0) for k in
                    ("p_below", "p_normal", "p_above", "normal_low", "normal_high", "expected")})
        t = o["seasons"]
        out["seasons"] = [{"year": int(y), "oni": num(r["oni"], 2), "total": num(r["total"], 0)}
                          for y, r in t.iterrows()]
    return out


# ----------------------------------------------------------------------------- peat
def peat_block(cube, admin, grid, country, adm1, adm2) -> dict | None:
    if admin is None or not D.has_peat(admin):
        return None
    km2 = D.peat_km2(country, adm1, ())
    if km2 is None or km2 < 50:
        return {"km2": num(km2, 0), "tooLittle": True}
    a_on = D.compute_peat(cube, admin, grid, country, adm1, adm2, (), True).harmonization.annual()
    a_off = D.compute_peat(cube, admin, grid, country, adm1, adm2, (), False).harmonization.annual()
    if a_on.empty or a_on["total"].sum() < 1:
        return {"km2": num(km2, 0), "tooLittle": True}
    yrs = a_on.index.union(a_off.index)
    return {"km2": num(km2, 0), "tooLittle": False, "years": [int(y) for y in yrs],
            "on": [num(v, 0) for v in a_on["total"].reindex(yrs)],
            "off": [num(v, 0) for v in a_off["total"].reindex(yrs)]}


# ----------------------------------------------------------------------------- checks
def official_block(res, country) -> dict | None:
    oc = D.official_check(res, country)
    if oc is None:
        return None
    from burncal.official import SOURCES
    t = oc["table"]
    return {"spearman": num(oc["spearman"], 2), "sameTop3": bool(oc["same_top3"]),
            "years": [int(y) for y in t.index], "fireDays": [num(v, 0) for v in t["fire_days"]],
            "official": [num(v, 0) for v in t["official"]], "sources": list(SOURCES.values())}


def gfed_block(res, country, adm1) -> dict | None:
    try:
        ba = D.burned_area_check(res, country, adm1)
    except Exception:  # noqa: BLE001 (too few overlapping months)
        return None
    if ba is None:
        return None
    y = ba["yearly"]
    return {"first": int(ba["first"].year), "last": int(ba["last"].year),
            "rMonthly": num(ba["r_monthly"], 2), "rAnomaly": num(ba["r_anomaly"], 2),
            "rYearlyRank": num(ba["r_yearly_rank"], 2),
            "top3Fire": [int(v) for v in ba["top3_fire"]], "top3Burned": [int(v) for v in ba["top3_burned"]],
            "years": [int(v) for v in y.index], "fireDays": [num(v, 0) for v in y["fire_days"]],
            "burnedKm2": [num(v, 0) for v in y["burned_km2"]],
            "step2012": num(ba["steps"]["step_2012"], 3), "step2018": num(ba["steps"]["step_2018"], 3),
            "naiveStep2012": num(ba["steps_naive"]["step_2012"], 3)}


# ----------------------------------------------------------------------------- events
def _where(e) -> str:
    parts = [x for x in (e.get("adm2"), e.get("adm1")) if isinstance(x, str) and x]
    if not parts and isinstance(e.get("country"), str):
        parts = [D.COUNTRY_NAMES.get(e["country"], e["country"])]
    return ", ".join(parts) or f"{e['lat']:.2f}°, {e['lon']:.2f}°"


def events_block(ev: pd.DataFrame, ev_end: pd.Timestamp, n_list: int = 50, growth: tuple | None = None) -> dict | None:
    """growth: (scores DataFrame indexed by event_id with p_big / p_long, summary dict) from
    scripts/build_growth.py, or None."""
    from burncal.events import active_events, compare_event
    if ev.empty:
        return None
    active = active_events(ev, ev_end, 5).nlargest(n_list, "area_km2")
    this_year = ev[ev["start"].dt.year == ev_end.year].nlargest(n_list, "area_km2")
    record = ev.nlargest(n_list, "area_km2")
    pick = pd.concat([active, this_year, record]).drop_duplicates("event_id")
    rows = []
    for _, e in pick.iterrows():
        c = compare_event(e, ev)
        bb = c["bigger_before"]
        rows.append({
            "id": int(e["event_id"]), "start": _str(e["start"]), "end": _str(e["end"]), "days": int(e["days"]),
            "km2": num(e["area_km2"], 1), "frpMax": num(e["frp_max"], 0), "peat": num(e["peat_share"], 3),
            "lat": num(e["lat"], 4), "lon": num(e["lon"], 4),
            "bbox": [num(e["west"], 4), num(e["south"], 4), num(e["east"], 4), num(e["north"], 4)],
            "where": _where(e),
            **_growth_fields(int(e["event_id"]), growth),
            "cmp": {"n": c["n"], "shareSmaller": num(c["share_smaller"], 4),
                    "biggerBefore": None if bb is None else {"km2": num(bb["area_km2"], 1),
                                                             "start": _str(bb["start"]), "where": _where(bb)}},
        })
    size = np.sort(ev["area_km2"].to_numpy())[::-1]
    ranks = np.unique(np.round(np.geomspace(1, len(size), num=min(len(size), 160))).astype(int))
    return {
        "n": int(len(ev)), "first": _str(ev["start"].min()), "end": _str(ev_end), "nActive": int(len(active)),
        "lists": {"active": [int(i) for i in active["event_id"]],
                  "thisYear": [int(i) for i in this_year["event_id"]],
                  "record": [int(i) for i in record["event_id"]]},
        "events": rows,
        "sizeCurve": [[int(r), num(size[r - 1], 2)] for r in ranks],
        "growth": _growth_summary(growth),
    }


def _growth_fields(event_id: int, growth) -> dict:
    if not growth or growth[0] is None or event_id not in growth[0].index:
        return {}
    r = growth[0].loc[event_id]
    return {"pBig": num(r["p_big"], 3), "pLong": num(r["p_long"], 3)}


def _growth_summary(growth) -> dict | None:
    if not growth or not growth[1]:
        return None
    t = growth[1].get("targets", {})
    keep = ("usable", "p_auc", "baseline_auc", "p_ap", "baseline_ap", "p_top1pct_precision",
            "baseline_top1pct_precision", "base_rate", "n")
    return {"bigKm2": growth[1].get("big_km2"), "longDays": growth[1].get("long_days"),
            "testYears": growth[1].get("test_years"),
            "targets": {k: {kk: (num(v.get(kk), 3) if kk != "usable" else bool(v.get(kk))) for kk in keep}
                        for k, v in t.items()}}


# ----------------------------------------------------------------------------- daily (date ranges)
def daily_block(daily: pd.DataFrame) -> dict | None:
    """date x satellite cell-days, sparse: per satellite the day offsets with fire and their counts."""
    if daily is None or daily.empty:
        return None
    d0 = daily.index.min().normalize()
    out = {"start": str(d0.date()), "sats": {}}
    for sat in daily.columns:
        s = daily[sat]
        s = s[s > 0]
        out["sats"][sat] = {"d": ((s.index.normalize() - d0).days).astype(int).tolist(),
                            "v": [int(v) for v in s.to_numpy()]}
    return out


# ----------------------------------------------------------------------------- raw totals by sub-area
def totals_block(cube, area: dict) -> dict | None:
    country, adm1, _ = area["query"]
    if area["level"] == "adm2":
        return None
    if area["level"] == "asia":
        country = None
    elif area["level"] == "group":
        country = tuple(country)
    t = D.totals_by_area(cube, country, adm1)
    if t.empty:
        return None
    key = t.columns[0]
    sats = [c for c in t.columns if c not in (key, "month")]
    return {"column": key, "sats": sats, "area": t[key].astype(str).tolist(), "month": t["month"].tolist(),
            "values": {s: [int(v) for v in t[s]] for s in sats}}


# ----------------------------------------------------------------------------- own areas (drawing)
def cells_block(frame: pd.DataFrame, rows: pd.DataFrame, last_day) -> dict | None:
    """The country's harmonized monthly fire days spread over 0.1 deg cells, in proportion to each
    month's raw detections from the satellite(s) the month comes from (burncal.playback.cell_frames
    at full resolution). The web app sums the cells inside a drawn shape."""
    from burncal.playback import cell_frames
    f = cell_frames(frame, rows, step="month", deg=0.1, last_day=last_day)
    if f.empty:
        return None
    months = sorted(set(f["period"]))
    midx = {m: i for i, m in enumerate(months)}
    f = f[f["value"] >= 0.005]
    return {"deg": 0.1, "months": months,
            "m": [midx[m] for m in f["period"]],
            "x": np.round(f["lon"].to_numpy() / 0.1 - 0.5).astype(int).tolist(),
            "y": np.round(f["lat"].to_numpy() / 0.1 - 0.5).astype(int).tolist(),
            "v": [round(float(v), 2) for v in f["value"]]}


def asmc_block() -> dict:
    """ASMC monthly haze review links, {"2019-09": [[title, url], ...]}."""
    from burncal.context import asmc_reviews
    try:
        rev = asmc_reviews()
    except Exception:  # noqa: BLE001
        return {}
    return {str(m): [[t, u] for t, u in links] for m, links in rev.items()}


# ----------------------------------------------------------------------------- land use (burncal.landuse)
def _annual_from_series(series: dict) -> pd.Series:
    """Harmonized total per calendar year (current year so far) from an exported area series."""
    s = pd.Series(series["value"], index=pd.PeriodIndex(series["months"], freq="M"), dtype=float).dropna()
    return s.groupby(s.index.year).sum()


def land_block(fine: pd.DataFrame, body: dict, concessions, source: dict) -> dict | None:
    """Fire inside concessions for an area (None when no fire falls in any concession)."""
    from burncal import landuse as L
    if fine is None or fine.empty or not concessions or body.get("summary") is None:
        return None
    pos = L.cells_with_position(fine)
    idx = L.assign_concessions(pos["lat"].to_numpy(), pos["lon"].to_numpy(), concessions)
    if (idx < 0).all():
        return None
    annual = _annual_from_series(body["series"])
    r = L.concession_fire(fine, idx, annual, len(concessions))
    s = body["summary"]
    year, through = int(s["thisYear"]), int(s["throughMonth"])
    base = [y for y in range(2019, year) if y in set(fine["year"].unique())]
    ch = L.concession_change(fine, idx, len(concessions), year, through, base)
    used = sorted(set(idx[idx >= 0].tolist()))
    rows = []
    for k in used:
        c = concessions[k]
        b = c.geom.bounds
        rows.append({
            "id": int(c.id), "name": c.name, "group": c.group, "kind": c.kind, "km2": num(c.km2, 1),
            "bbox": [num(b[0], 4), num(b[1], 4), num(b[2], 4), num(b[3], 4)],
            "fireDays": [num(v, 1) for v in r["per"][k]],
            "this": num(ch.loc[k, "this"], 0), "typical": num(ch.loc[k, "typical"], 1),
            "changePct": num(ch.loc[k, "change_pct"], 1),
        })
    return {"source": source, "years": r["years"], "total": [num(v, 1) for v in r["total"]],
            "inside": [num(v, 1) for v in r["inside"]], "year": year, "throughMonth": through, "baseYears": base,
            "concessions": rows}


def concessions_geojson(concessions, tol: float = 0.002) -> dict:
    """Simplified concession outlines for the map (feature id = concession id)."""
    import json as _json

    import shapely
    feats = []
    for c in concessions:
        g = shapely.set_precision(shapely.simplify(c.geom, tol, preserve_topology=True), 0.0001)
        if g.is_empty:
            continue
        feats.append({"type": "Feature", "id": int(c.id),
                      "properties": {"id": int(c.id), "name": c.name, "group": c.group, "km2": num(c.km2, 1)},
                      "geometry": _json.loads(shapely.to_geojson(g))})
    return {"type": "FeatureCollection", "features": feats}


def spots_block(fine: pd.DataFrame, last_year: int, concessions, peat_cells, max_spots: int = 5000,
                min_years: int = 3) -> dict | None:
    """Repeat burn spots of an area: cells that burned in at least `min_years` VIIRS years."""
    from burncal import landuse as L
    if fine is None or fine.empty:
        return None
    s = L.repeat_spots(fine, last_year)
    if s.empty:
        return None
    n_years = last_year - L.SPOTS_FIRST_YEAR + 1
    hist = s["years"].value_counts().reindex(range(1, n_years + 1), fill_value=0)
    top = s[s["years"] >= min_years].sort_values(["years", "cd"], ascending=False).head(max_spots)
    lat, lon = top["lat"].to_numpy(), top["lon"].to_numpy()
    conc = L.assign_concessions(lat, lon, concessions) if concessions else np.full(len(top), -1)
    peat = L.on_peat(lat, lon, peat_cells)
    names = {}
    for k in sorted(set(conc[conc >= 0].tolist())):
        names[int(concessions[k].id)] = concessions[k].name
    return {
        "firstYear": L.SPOTS_FIRST_YEAR, "lastYear": int(last_year), "minYears": min_years,
        "cellsBurned": int(len(s)), "histogram": [int(v) for v in hist],
        "truncated": bool((s["years"] >= min_years).sum() > max_spots),
        "lon": [round(float(v), 4) for v in lon], "lat": [round(float(v), 4) for v in lat],
        "years": [int(v) for v in top["years"]], "mask": [int(v) for v in top["mask"]],
        "last": [int(v) for v in top["last"]], "cd": [int(v) for v in top["cd"]],
        "peat": [int(v) for v in peat],
        "conc": [int(concessions[k].id) if k >= 0 else -1 for k in conc.tolist()],
        "concNames": {str(k): v for k, v in names.items()},
    }


# ----------------------------------------------------------------------------- short-range forecast
def forecast_block(area: dict, latest: pd.DataFrame | None, history: pd.DataFrame | None, summary: dict) -> dict | None:
    """Next-week and weeks-2-4 forecast for an area (scripts/build_forecast.py), with its backtest."""
    if latest is None or area["level"] not in ("country", "adm1", "adm2"):
        return None
    country, adm1, adm2 = area["query"]
    level = area["level"]
    key = "|".join(x for x in (country, adm1, adm2) if x)
    aid = f"{level}:{key}"
    row = latest[latest["area"] == aid]
    if row.empty:
        return None
    r = row.iloc[0]
    out = {"issued": r["issued"], "recentWeek": num(r["recent_y"], 0), "horizons": {},
           "weatherUsed": bool(summary.get("weather_used", False))}
    if pd.notna(r.get("w_rain_30", np.nan)):
        anom = r.get("w_rain_30_anom", np.nan)
        out["weather"] = {
            "rain30mm": num(np.expm1(r["w_rain_30"]), 0),
            # rain in the last 30 days as a share of the usual amount for these dates (from the log anomaly)
            "rain30OfUsual": num(np.exp(anom), 2) if pd.notna(anom) else None,
            "dryDays": num(r.get("w_dry_days"), 0),
            "soil": num(r.get("w_soil"), 2), "soilAnom": num(r.get("w_soil_anom"), 3),
            "tmax7": num(r.get("w_tmax_7"), 1),
        }
    for h, label in (("h1", "next 7 days"), ("h4", "weeks 2-4")):
        out["horizons"][h] = {
            "label": label, "usable": bool(r[f"{h}_usable"]),
            "q10": num(r[f"{h}_q10"], 0), "q50": num(r[f"{h}_q50"], 0), "q90": num(r[f"{h}_q90"], 0),
            "usual": num(r[f"{h}_usual"], 0), "pAbove": num(r[f"{h}_p_above"], 2),
            "skillPersist": num(r[f"{h}_skill_persist"], 3), "skillClim": num(r[f"{h}_skill_clim"], 3),
            "coverage": num(r[f"{h}_coverage"], 3), "hit": num(r[f"{h}_hit"], 3), "n": num(r[f"{h}_n"], 0),
        }
    if history is not None:
        hh = history[history["area"] == aid].sort_values("week_end").tail(30)
        out["history"] = {
            "targetEnd": [str((pd.Timestamp(w) + pd.Timedelta(days=7)).date()) for w in hh["week_end"]],
            "actual": [num(v, 0) for v in hh["actual_h1"]],
            "q10": [num(v, 0) for v in hh["h1_q10"]], "q50": [num(v, 0) for v in hh["h1_q50"]],
            "q90": [num(v, 0) for v in hh["h1_q90"]], "usual": [num(v, 0) for v in hh["h1_clim"]],
        }
    out["overall"] = summary.get("overall", {})
    out["testYears"] = summary.get("test_years", [])
    return out
