"""Export the harmonized record as small static JSON files for the Next.js web app (web/).

The web app has no server: every number it shows is computed here, with the same package
data-access code (app/data.py, burncal.*), and written to web/public/data/:

    index.json              area tree (ids, names, levels, bounding boxes), last data day, ENSO years
    area/<id>.json          monthly harmonized series with likely range, yearly totals, headline
                            numbers, notes, and this year's change for each sub-area
    frames/<id>.year.json   playback cells, year by year (all years)
    frames/<id>.month.json  playback cells, month by month (latest 3 years)
    geo/<id>.json           simplified borders of the sub-areas (what the map shows and clicks)
    detail/<id>.json        method (raw satellites, steps, seams, satellite differences), outlook, peat, checks
    events/<id>.json        fire events: burning now, biggest this year / on record, size curve
    daily/<id>.json         daily cell-days per satellite (date-range comparisons)
    totals/<id>.json        raw monthly fire days per sub-area and satellite (CSV download)
    cells/<iso>.json        the country's harmonized monthly fire days per 0.1 deg cell (own areas)
    recent/<iso>.json       the latest detections (real points, not converted)

Playback dots come from data/processed/fine_cells (scripts/build_fine_cells.py) when present:
~2 km cells drawn at the detections' mean position; else from the 0.1 deg daily grid.
    asmc.json               ASMC haze review links per month

Area ids are URL paths: "" (all of Asia), "southeast-asia", "mys", "mys/sarawak",
"mys/sarawak/miri". The root area is written as "_all".

    python scripts/export_web.py                    # everything (about 20-40 min)
    python scripts/export_web.py --countries MYS    # groups + Malaysia only; other areas stay in index.json
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
import time
import unicodedata
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

import data as D  # noqa: E402  (app/data.py)
from burncal import daily as DL  # noqa: E402
from burncal.playback import cell_frames  # noqa: E402
from burncal.regions import OTHER_ISO3  # noqa: E402

# fire-event columns the export reads (scripts/export_web_views.events_block, burncal.alerts, data.events_in)
EVENT_COLS = ["event_id", "start", "end", "days", "area_km2", "frp_max", "peat_share", "lat", "lon",
              "west", "south", "east", "north", "country", "adm1", "adm2"]

import export_web_views as V  # noqa: E402  (scripts/export_web_views.py)

UNIT = "fire days"
MONTH_YEARS = 3  # month-by-month playback covers the latest N years


# ----------------------------------------------------------------------------- helpers
def slug(text: str) -> str:
    t = unicodedata.normalize("NFKD", str(text).replace("đ", "d").replace("Đ", "D"))
    t = "".join(c for c in t if not unicodedata.combining(c))  # drop accents, keep dashes as separators
    t = re.sub(r"[^a-zA-Z0-9]+", "-", t).strip("-").lower()
    return t or "area"


def num(x, nd: int = 1):
    """JSON-safe rounded number (None for NaN/inf)."""
    if x is None:
        return None
    try:
        x = float(x)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(x):
        return None
    return round(x, nd)


def file_id(area_id: str) -> str:
    return area_id or "_all"


def write_json(path: Path, obj) -> int:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    path.write_text(text, encoding="utf-8")
    return len(text)


# ----------------------------------------------------------------------------- area tree
def build_tree(cube: pd.DataFrame, countries: set[str] | None) -> list[dict]:
    """Flat list of areas with parent/children ids. `query` holds the (country, adm1, adm2)
    arguments of app/data.py for that area."""
    opts = D.region_options(cube)
    if countries:
        opts = {k: v for k, v in opts.items() if k in countries}
    areas: list[dict] = []
    root = {"id": "", "name": "Asia", "level": "asia", "parent": None, "children": [],
            "query": [None, None, None]}
    areas.append(root)
    in_group: dict[str, str] = {}
    for label, members in D.GROUPS.items():
        if members is None:
            continue
        gid = slug(label.removeprefix("All "))
        kids = [m for m in members if m in opts]
        if not kids:
            continue
        areas.append({"id": gid, "name": label.removeprefix("All "), "level": "group", "parent": "",
                      "children": [], "query": [list(members), None, None]})
        root["children"].append(gid)
        for m in kids:
            in_group[m] = gid
    for iso, provs in opts.items():
        cid = iso.lower()
        # countries outside Asia (regions.OTHER_ISO3) are top-level areas of their own, never under "Asia"
        parent = None if iso in OTHER_ISO3 else in_group.get(iso, "")
        areas.append({"id": cid, "name": D.COUNTRY_NAMES[iso], "level": "country", "parent": parent,
                      "children": [], "query": [iso, None, None], "iso": iso})
        if parent is not None:
            next(a for a in areas if a["id"] == parent)["children"].append(cid)
        country = areas[-1]
        used1: set[str] = set()
        for a1, districts in provs.items():
            s1 = slug(a1)
            while s1 in used1:
                s1 += "-x"
            used1.add(s1)
            pid = f"{cid}/{s1}"
            areas.append({"id": pid, "name": a1, "level": "adm1", "parent": cid, "children": [],
                          "query": [iso, a1, None], "iso": iso})
            country["children"].append(pid)
            prov = areas[-1]
            used2: set[str] = set()
            for a2 in districts:
                s2 = slug(a2)
                while s2 in used2:
                    s2 += "-x"
                used2.add(s2)
                did = f"{pid}/{s2}"
                areas.append({"id": did, "name": a2, "level": "adm2", "parent": pid, "children": [],
                              "query": [iso, a1, a2], "iso": iso})
                prov["children"].append(did)
    return areas


def child_level(area: dict) -> str | None:
    return {"asia": "country", "group": "country", "country": "adm1", "adm1": "adm2"}.get(area["level"])


def child_key(child: dict) -> str:
    """Name a sub-area has in load_areas / area_change (ISO3 for countries, else the name)."""
    return child["iso"] if child["level"] == "country" else child["name"]


# ----------------------------------------------------------------------------- per-area content
def series_block(res) -> dict:
    f = res.harmonization.frame
    f = f[f["harmonized"].notna()]
    src = f["source"].astype(str)
    return {
        "months": [str(m) for m in f.index],
        "value": [num(v) for v in f["harmonized"]],
        "lower": [num(v) for v in f["lower"]],
        "upper": [num(v) for v in f["upper"]],
        "estimated": [not s.endswith("measured") for s in src],
        "source": list(src),
    }


def annual_block(res) -> dict:
    a = res.harmonization.annual()
    return {
        "years": [int(y) for y in a.index],
        "total": [num(v) for v in a["total"]],
        "lower": [num(v) for v in a["lower"]],
        "upper": [num(v) for v in a["upper"]],
        "estimatedShare": [num(v, 3) for v in a["estimated_share"]],
    }


def summary_block(res) -> dict | None:
    try:
        s = D.summary_numbers(res)
    except Exception:  # too little data for a season comparison
        return None
    return {
        "peakMonth": s["peak_month"], "peakShare": num(s["peak_share"], 3),
        "busiestYear": s["busiest_year"], "busiestYearTotal": num(s["busiest_year_total"]),
        "busiestYearEstimated": s["busiest_year_estimated"], "busiestTies": s["busiest_ties"],
        "partialMonth": s["partial_month"], "thisYear": s["this_year"], "throughMonth": s["through_month"],
        "thisYearToDate": num(s["this_year_to_date"]), "rank": s["rank"], "nYears": s["n_years"],
        "pctVsMedian": num(s["pct_vs_median"]),
    }


def change_block(cube, area: dict, kids: list[dict]) -> dict | None:
    lvl = child_level(area)
    if not kids or lvl is None:
        return None
    country, adm1, _ = area["query"]
    country = tuple(country) if isinstance(country, list) else country
    try:
        ch = D.area_change(cube, lvl, country, adm1)
    except Exception:
        return None
    rows = {}
    for k in kids:
        key = child_key(k)
        if key in ch.index:
            r = ch.loc[key]
            rows[k["id"]] = [num(r["this"]), num(r["typical"]), num(r["change_pct"])]
    return {"year": int(ch.attrs["year"]), "throughMonth": int(ch.attrs["through_month"]),
            "baseYears": [int(y) for y in ch.attrs["base_years"]], "rows": rows}


def fine_frames_block(frame: pd.DataFrame, fine: pd.DataFrame, step: str, last_day) -> dict | None:
    """Playback dots at the detections' mean position (burncal.fine), ~2 km where the area allows."""
    from burncal.fine import fine_frames
    f = fine_frames(frame, fine, step=step, month_years=MONTH_YEARS)
    if f.empty:
        return None
    deg = float(f.attrs["deg"])
    totals = f.attrs["totals"]
    periods = list(totals.index)
    pidx = {p: i for i, p in enumerate(periods)}
    f = f[f["value"] > 0.005]
    partial = None
    if last_day is not None:
        ld = pd.Timestamp(last_day)
        last = periods[-1]
        if step == "year" and (ld.month, ld.day) != (12, 31) and last == str(ld.year):
            partial = last
        elif step == "month" and ld.day != ld.days_in_month and last == f"{ld.year}-{ld.month:02d}":
            partial = last
    return {
        "step": step, "deg": deg, "periods": periods, "totals": [num(v) for v in totals],
        "partial": partial,
        # dot = mean position of the detections in a display cell of `deg` degrees
        "p": [pidx[p] for p in f["period"]],
        "lon": [round(float(v), 4) for v in f["lon"]],
        "lat": [round(float(v), 4) for v in f["lat"]],
        "v": [num(v, 2) for v in f["value"]],
    }


def recent_block(recent, last_day) -> dict | None:
    """Latest real detections (not converted): position, days before the last day, FRP, satellite."""
    if recent is None or recent.empty:
        return None
    ld = pd.Timestamp(last_day).normalize()
    # one satellite only, so the same fire is not drawn twice (NOAA-20 when it flew)
    if (recent["satellite"] == "NOAA20").any():
        recent = recent[recent["satellite"] == "NOAA20"]
    r = recent.sort_values("solar_date")
    sats = sorted(r["satellite"].astype(str).unique())
    return {
        "lastDay": str(ld.date()), "sats": sats,
        "lon": [round(float(v), 4) for v in r["longitude"]],
        "lat": [round(float(v), 4) for v in r["latitude"]],
        "age": ((ld - pd.to_datetime(r["solar_date"]).dt.normalize()).dt.days).astype(int).tolist(),
        "frp": [num(v, 1) for v in r["frp"]],
        "sat": [sats.index(x) for x in r["satellite"].astype(str)],
        "night": [1 if d == "N" else 0 for d in r["daynight"].astype(str)],
    }


def frames_block(frame: pd.DataFrame, rows: pd.DataFrame, step: str, last_day) -> dict | None:
    if step == "month":
        last = frame["harmonized"].dropna().index.max()
        frame = frame[frame.index.year > last.year - MONTH_YEARS]
    f = cell_frames(frame, rows, step=step, last_day=last_day)
    if f.empty:
        return None
    deg = float(f.attrs["deg"])
    totals = f.attrs["totals"]
    periods = list(totals.index)
    pidx = {p: i for i, p in enumerate(periods)}
    f = f[f["value"] > 0.05]
    return {
        "step": step, "deg": deg, "periods": periods, "totals": [num(v) for v in totals],
        "partial": f.attrs["partial"],
        # cell centre = ((x + 0.5) * deg, (y + 0.5) * deg); v = NOAA-20-equivalent fire days
        "p": [pidx[p] for p in f["period"]],
        "x": np.round(f["lon"].to_numpy() / deg - 0.5).astype(int).tolist(),
        "y": np.round(f["lat"].to_numpy() / deg - 0.5).astype(int).tolist(),
        "v": [num(v) for v in f["value"]],
    }


def geo_block(area: dict, kids: list[dict], by_id: dict) -> tuple[dict | None, dict]:
    """Sub-area borders as GeoJSON (feature id = sub-area id) and each sub-area's bbox."""
    lvl = child_level(area)
    if lvl is None:
        return None, {}
    country, adm1, _ = area["query"]
    if area["level"] == "asia":
        country = None
    elif area["level"] == "group":
        country = tuple(country)
    ar = D.load_areas(lvl, country, adm1)
    if ar is None:
        return None, {}
    key_to_id = {child_key(k): k["id"] for k in kids}
    if area["level"] == "asia":  # the Asia map shows countries, but the root's children are regions: link them all
        key_to_id.update({child_key(k): k["id"] for k in by_id.values() if k["level"] == "country" and k["parent"] is not None})
    feats, bboxes = [], {}
    for f in ar["geojson"]["features"]:
        key = f["id"]
        cid = key_to_id.get(key)
        name = ar["names"][key]
        f = dict(f)
        f["id"] = cid or f"_{slug(key)}"
        f["properties"] = {"id": cid, "name": name, "km2": num(ar["km2"][key], 0)}
        feats.append(f)
        if cid:
            bboxes[cid] = [num(v, 3) for v in ar["bounds"][key]]
    return {"type": "FeatureCollection", "features": feats}, bboxes


def merge_index(old: dict, new: dict) -> dict:
    """Index after a partial export (--countries): areas written now replace their old entries, every other
    old area is kept, and an area's children are the old ones plus any new ones (old order first)."""
    by_new = {a["id"]: a for a in new["areas"]}
    out = []
    for a in old.get("areas", []):
        b = by_new.pop(a["id"], None)
        if b is None:
            out.append(a)
        else:
            out.append({**b, "children": a["children"] + [c for c in b["children"] if c not in a["children"]]})
    out.extend(by_new.values())
    return {**new, "areas": out}


def _bounds(geom: dict) -> list[float]:
    xs, ys = [], []

    def walk(c):
        if c and isinstance(c[0], (int, float)):
            xs.append(c[0])
            ys.append(c[1])
        else:
            for x in c:
                walk(x)
    walk(geom["coordinates"])
    return [num(min(xs), 3), num(min(ys), 3), num(max(xs), 3), num(max(ys), 3)]


def index_entries_from_disk(areas: list[dict], out: Path) -> list[dict]:
    """Index entries for areas whose files an earlier (interrupted) run wrote, read back from those files:
    bounding boxes from the border files, flags from which files exist. Used by --events-only."""
    by_id = {a["id"]: a for a in areas}
    bboxes: dict[str, list] = {}
    for a in areas:
        g = out / "geo" / f"{file_id(a['id'])}.json"
        if g.exists():
            for f in json.loads(g.read_text(encoding="utf-8"))["features"]:
                cid = f["properties"].get("id")
                if cid in by_id and f.get("geometry"):
                    bboxes[cid] = _bounds(f["geometry"])
    for a in sorted(areas, key=lambda a: -(a["id"].count("/") + bool(a["id"]))):  # deepest first
        if a["id"] not in bboxes:
            bs = np.array([bboxes[c] for c in a["children"] if c in bboxes])
            if len(bs):
                bboxes[a["id"]] = [float(bs[:, 0].min()), float(bs[:, 1].min()), float(bs[:, 2].max()), float(bs[:, 3].max())]
    rows = []
    for a in areas:
        fid = file_id(a["id"])
        has = lambda d, name=fid: (out / d / f"{name}.json").exists()  # noqa: E731
        iso = (a.get("iso") or "").lower()
        e = {"id": a["id"], "name": a["name"], "level": a["level"], "parent": a["parent"], "children": a["children"],
             "bbox": bboxes.get(a["id"]), "hasGeo": has("geo"),
             "frames": [st for st in ("year", "month") if has("frames", f"{fid}.{st}")],
             "events": has("events"), "cells": a["level"] == "country" and has("cells", iso),
             "recent": a["level"] == "country" and has("recent", iso), "spots": has("spots"), "land": has("land"),
             "forecast": has("forecast")}
        if not has("area"):
            e["empty"] = True
        rows.append(e)
    return rows


# ----------------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=ROOT / "web" / "public" / "data")
    ap.add_argument("--countries", nargs="*", help="only these ISO3 countries (groups are always written)")
    ap.add_argument("--no-frames", action="store_true", help="skip the playback files")
    ap.add_argument("--no-events", action="store_true", help="skip the fire-event files")
    ap.add_argument("--no-peat", action="store_true", help="skip the peat split (two extra conversions per area)")
    ap.add_argument("--events-only", action="store_true",
                    help="only rewrite events/ for an existing export in --out (after build_events renumbers the "
                         "events), and add areas an interrupted run wrote to its index")
    ap.add_argument("--land-only", action="store_true",
                    help="only (re)write land/, spots/ and forecast/ for an existing export in --out, and update its index")
    args = ap.parse_args(argv)
    out: Path = args.out
    t0 = time.time()

    cube = D.get_cube()
    sizes = {"area": 0, "frames": 0, "geo": 0, "detail": 0, "events": 0, "daily": 0, "totals": 0, "cells": 0,
             "recent": 0, "spots": 0, "land": 0, "forecast": 0}

    # land use: concessions (CC BY 4.0) and the peat map, for land/ and spots/
    from burncal import landuse as L
    conc_path = ROOT / "data" / "external" / "concessions" / "sarawak_oil_palm.geojson"
    concessions = L.load_concessions(conc_path) if conc_path.exists() else []
    conc_source = {
        "name": "Sarawak oil palm concessions",
        "credit": "SADIA, Aidenvironment & Earthsight Investigations, via Global Forest Watch",
        "license": "CC BY 4.0",
        "note": "Licence boundaries from EIA reports and a 2010 Sarawak Forest Department map; may be incomplete or outdated.",
    }
    peat_path = ROOT / "data" / "external" / "peat_cells.parquet"
    peat_cells = pd.read_parquet(peat_path) if peat_path.exists() else None
    # short-range forecast (scripts/build_forecast.py)
    # Asia has one model (forecast/); countries outside Asia have their own (forecast_other/, built with
    # --countries ARG --out data/processed/forecast_other), so adding them never changes an Asian forecast
    import json as _json_fc

    def load_fc(d: Path):
        return (pd.read_parquet(d / "latest.parquet") if (d / "latest.parquet").exists() else None,
                pd.read_parquet(d / "history.parquet") if (d / "history.parquet").exists() else None,
                _json_fc.loads((d / "summary.json").read_text(encoding="utf-8")) if (d / "summary.json").exists() else {})

    fc_main = load_fc(ROOT / "data" / "processed" / "forecast")
    fc_other = load_fc(ROOT / "data" / "processed" / "forecast_other")

    def fc_block(a: dict):
        return V.forecast_block(a, *(fc_other if a.get("iso") in OTHER_ISO3 else fc_main))

    def write_land(a: dict, body: dict, fine) -> None:
        """Extras computed from finished inputs: forecast, repeat spots, concessions."""
        fid = file_id(a["id"])
        fb_ = fc_block(a)
        if fb_ is not None:
            sizes["forecast"] += write_json(out / "forecast" / f"{fid}.json", fb_)
            a["forecast"] = True
        if a["level"] not in ("country", "adm1", "adm2") or fine is None or fine.empty or not body.get("summary"):
            return
        sb = V.spots_block(fine, int(body["summary"]["thisYear"]), concessions, peat_cells)
        if sb is not None:
            sizes["spots"] += write_json(out / "spots" / f"{fid}.json", sb)
            a["spots"] = True
        lb = V.land_block(fine, body, concessions, conc_source)
        if lb is not None:
            sizes["land"] += write_json(out / "land" / f"{fid}.json", lb)
            a["land"] = True

    heavy = not args.land_only  # land-only needs neither the daily tables nor the events
    # the admin table is small; the grid (~31 M rows for all of Asia) is read one country at a time
    admin = DL.load_daily(D.DAILY_ADMIN) if heavy and D.has_daily() else None
    grid = None
    grid_cache: dict = {}

    def grid_rows(isos_: list[str]):
        key_ = tuple(sorted(isos_))
        if key_ not in grid_cache:
            grid_cache.clear()
            grid_cache[key_] = DL.load_daily(D.DAILY_GRID, countries=list(key_)) if D.has_daily() else None
        return grid_cache[key_]
    last_day = DL.last_complete_day(DL.daily_for_region(admin, None)) if admin is not None else None
    ev_by_country, ev_end = {}, None
    if heavy and not args.no_events and D.has_events():
        # only the columns events_block / alerts use, region names as categories: ~1.5 GB -> well under 1 GB
        ev_all = D.get_events(columns=EVENT_COLS, compact=True)
        ev_end = min(last_day, ev_all["end"].max()) if last_day is not None else ev_all["end"].max()
        ev_by_country = {c: g for c, g in ev_all.groupby("country", observed=True)}
        del ev_all
    # fire-growth models (scripts/build_growth.py): one for Asia, one for Argentina (growth_other)
    import json as _json_g

    def load_growth(gdir: Path):
        if not (gdir / "scores.parquet").exists():
            return None
        return (pd.read_parquet(gdir / "scores.parquet").set_index("event_id"),
                _json_g.loads((gdir / "summary.json").read_text(encoding="utf-8")))

    growth_main = load_growth(ROOT / "data" / "processed" / "growth")
    growth_other = load_growth(ROOT / "data" / "processed" / "growth_other")

    def growth_for(a: dict):
        return growth_other if a.get("iso") in OTHER_ISO3 else growth_main

    fine_dir = ROOT / "data" / "processed" / "fine_cells"
    recent_dir = ROOT / "data" / "processed" / "recent"
    fine_cache: dict = {}
    coarse_cache: dict = {}

    def fine_country(iso: str):
        if iso not in fine_cache:
            p = fine_dir / f"{iso}.parquet"
            fine_cache.clear()  # keep one country in memory
            fine_cache[iso] = pd.read_parquet(p) if p.exists() else None
        return fine_cache[iso]

    def coarse_country(iso: str):
        """A country's fine cells merged to 0.1 deg (positions kept as sums), for regions and Asia."""
        if iso not in coarse_cache:
            f = fine_country(iso)
            if f is None:
                coarse_cache[iso] = None
            else:
                g = f.assign(fy=(f["fy"] // 5) * 5, fx=(f["fx"] // 5) * 5)
                coarse_cache[iso] = g.groupby(["satellite", "year", "month", "fy", "fx"], observed=True)[
                    ["cd", "n", "slat", "slon"]].sum().reset_index().assign(adm1="", adm2="")
        return coarse_cache[iso]

    def fine_for(a: dict):
        country, adm1, adm2 = a["query"]
        if a["level"] in ("asia", "group"):
            isos_ = D.isos(None if a["level"] == "asia" else tuple(country))
            parts = [c for c in (coarse_country(i) for i in isos_) if c is not None]
            return pd.concat(parts, ignore_index=True) if parts else None
        f = fine_country(country)
        if f is None:
            return None
        if adm1:
            f = f[f["adm1"] == adm1]
        if adm2:
            f = f[f["adm2"] == adm2]
        return f

    def load_recent(iso: str):
        p = recent_dir / f"{iso}.parquet"
        return pd.read_parquet(p) if p.exists() else None

    areas = build_tree(cube, set(args.countries) if args.countries else None)
    by_id = {a["id"]: a for a in areas}

    from burncal import alerts as AL
    alerts: list = []

    def area_alerts(a: dict, res, country, adm1, adm2, ev) -> list:
        out_ = []
        d7 = DL.daily_for_region(admin, country, adm1, adm2)
        start = (pd.Timestamp(last_day) - pd.Timedelta(days=6)).normalize()
        if len(d7):
            tot = DL.window_totals(res.harmonization.frame, d7, start, last_day, last_day)
            w = DL.compare_window(tot, pd.Timestamp(last_day).year) if len(tot) else {}
            al = AL.surge_alert(a["id"], a["name"], w, f"{start:%d %b}", f"{pd.Timestamp(last_day):%d %b %Y}")
            if al:
                out_.append(al)
        fb = fc_block(a)
        al = AL.forecast_alert(a["id"], a["name"], fb["horizons"]["h1"] if fb else None)
        if al:
            out_.append(al)
        if ev is not None and len(ev):
            growth = growth_for(a)
            p_big = growth[0]["p_big"] if growth else None
            usable = bool(growth and growth[1].get("targets", {}).get("big", {}).get("usable"))
            out_.extend(AL.big_fire_alerts(a["id"], a["name"], ev, last_day, p_big, usable))
        return out_

    if args.events_only:
        index_path = out / "index.json"
        index = json.loads(index_path.read_text(encoding="utf-8"))
        known = {e["id"] for e in index["areas"]}
        added = index_entries_from_disk([a for a in areas if a["id"] not in known], out)
        index = merge_index(index, {**index, "areas": added})
        flags, n = {}, 0
        for a in areas:
            country, adm1, adm2 = a["query"]
            country = tuple(country) if isinstance(country, list) else country
            p_ = out / "events" / f"{file_id(a['id'])}.json"
            parts = [ev_by_country[c] for c in D.isos(country) if c in ev_by_country]
            eb = V.events_block(D.events_in(pd.concat(parts), country, adm1, adm2), ev_end, growth=growth_for(a)) if parts else None
            if eb is not None and (out / "area" / f"{file_id(a['id'])}.json").exists():
                sizes["events"] += write_json(p_, eb)
                n += 1
            elif p_.exists():
                p_.unlink()  # its old ids point at other fires now
            flags[a["id"]] = eb is not None
        for e in index["areas"]:
            if e["id"] in flags:
                e["events"] = flags[e["id"]] and not e.get("empty", False)
        write_json(index_path, index)
        print(f"events-only: {n} event files, {len(added)} areas added to the index, {time.time() - t0:,.0f} s")
        return 0

    if args.land_only:
        import json as _json
        index_path = out / "index.json"
        index = _json.loads(index_path.read_text(encoding="utf-8"))
        flags = {}
        for a in areas:
            p_ = out / "area" / f"{file_id(a['id'])}.json"
            if not p_.exists():
                continue
            write_land(a, _json.loads(p_.read_text(encoding="utf-8")), fine_for(a))
            flags[a["id"]] = (a.get("spots", False), a.get("land", False), a.get("forecast", False))
        for e in index["areas"]:
            if e["id"] in flags:
                e["spots"], e["land"], e["forecast"] = flags[e["id"]]
        write_json(index_path, index)
        if concessions and any(v[1] for v in flags.values()):
            write_json(out / "land" / "_concessions.json", V.concessions_geojson(concessions))
        mb = {k: round(v / 1e6, 1) for k, v in sizes.items() if v}
        print(f"land-only: {sum(v[0] for v in flags.values())} spot files, {sum(v[1] for v in flags.values())} "
              f"concession files, {sum(v[2] for v in flags.values())} forecast files in {time.time() - t0:,.0f} s; MB: {mb}")
        return 0
    bboxes: dict[str, list] = {}

    # borders first: they give every sub-area its bounding box
    for a in areas:
        kids = [by_id[c] for c in a["children"]]
        gj, bb = geo_block(a, kids, by_id)
        bboxes.update(bb)
        if gj is not None:
            sizes["geo"] += write_json(out / "geo" / f"{file_id(a['id'])}.json", gj)
            a["hasGeo"] = True
    for a in sorted(areas, key=lambda a: -(a["id"].count("/") + bool(a["id"]))):  # deepest first
        if a["id"] not in bboxes and a["children"]:
            bs = np.array([bboxes[c] for c in a["children"] if c in bboxes])
            if len(bs):
                bboxes[a["id"]] = [float(bs[:, 0].min()), float(bs[:, 1].min()),
                                   float(bs[:, 2].max()), float(bs[:, 3].max())]

    for i, a in enumerate(areas, 1):
        country, adm1, adm2 = a["query"]
        country = tuple(country) if isinstance(country, list) else country
        if a["level"] not in ("asia", "group"):
            coarse_cache.clear()  # merged cells of every country are only needed for Asia and its regions
        try:
            res = D.compute(cube, country, adm1, adm2)
        except Exception as e:  # noqa: BLE001
            print(f"  skip {a['id'] or 'Asia'}: {e}")
            a["empty"] = True
            continue
        kids = [by_id[c] for c in a["children"]]
        rough = D.rough_years_note(res)
        body = {
            "id": a["id"], "name": a["name"], "level": a["level"],
            "series": series_block(res), "annual": annual_block(res), "summary": summary_block(res),
            "notes": {"tooFewFrom": D.too_few_fires(res), "roughYearsPct": num(rough)},
            "childChange": change_block(cube, a, kids),
        }
        fid = file_id(a["id"])
        sizes["area"] += write_json(out / "area" / f"{fid}.json", body)

        # detail views
        sub = a["level"] in ("asia", "group", "country", "adm1")
        detail = {
            "raw": V.raw_block(res), "steps": V.steps_block(res), "seams": V.seams_block(res),
            "satDiff": V.sat_diff_block(country, adm1) if sub else None,
            "outlook": V.outlook_block(res),
            "peat": None if args.no_peat else V.peat_block(cube, admin, grid, country, adm1, adm2),
            "official": V.official_block(res, country) if a["level"] == "country" else None,
            "gfed": V.gfed_block(res, country, adm1) if sub else None,
        }
        sizes["detail"] += write_json(out / "detail" / f"{fid}.json", detail)
        if admin is not None:
            db = V.daily_block(DL.daily_for_region(admin, country, adm1, adm2))
            if db is not None:
                sizes["daily"] += write_json(out / "daily" / f"{fid}.json", db)
        tb = V.totals_block(cube, a)
        if tb is not None:
            sizes["totals"] += write_json(out / "totals" / f"{fid}.json", tb)
        ev = None
        if ev_by_country:
            parts = [ev_by_country[c] for c in D.isos(country) if c in ev_by_country]
            if parts:
                ev = D.events_in(pd.concat(parts), country, adm1, adm2)
                eb = V.events_block(ev, ev_end, growth=growth_for(a))
                if eb is not None:
                    sizes["events"] += write_json(out / "events" / f"{fid}.json", eb)
                    a["events"] = True

        if admin is not None and not args.no_frames:
            fine = fine_for(a)
            have_fine = fine is not None and not fine.empty
            rows = None
            # grid rows are needed for drawn areas (country files) and as a fallback without fine cells
            if a["level"] == "country" or (not have_fine and a["level"] not in ("asia", "group")):
                g_ = grid_rows([a["iso"]] if a["level"] != "asia" and a.get("iso") else D.isos(country))
                rows = DL.grid_for_region(g_, country, adm1, adm2) if g_ is not None and len(g_) else None
            if a["level"] == "country" and rows is not None:
                cb = V.cells_block(res.harmonization.frame, rows, last_day)
                if cb is not None:
                    sizes["cells"] += write_json(out / "cells" / f"{a['iso'].lower()}.json", cb)
                    a["cells"] = True
                rb = recent_block(load_recent(a["iso"]), last_day)
                if rb is not None:
                    sizes["recent"] += write_json(out / "recent" / f"{a['iso'].lower()}.json", rb)
                    a["recent"] = True
            write_land(a, body, fine)
            for step in ("year", "month"):
                if have_fine:
                    fb = fine_frames_block(res.harmonization.frame, fine, step, last_day)
                else:
                    fb = frames_block(res.harmonization.frame, rows, step, last_day) if rows is not None else None
                if fb is not None:
                    sizes["frames"] += write_json(out / "frames" / f"{file_id(a['id'])}.{step}.json", fb)
                    a.setdefault("frames", []).append(step)
        # alerts (burncal.alerts): never let them stop the export
        if a["level"] in ("country", "adm1", "adm2") and last_day is not None:
            try:
                alerts.extend(area_alerts(a, res, country, adm1, adm2, ev))
            except Exception as e_:  # noqa: BLE001
                print(f"  alerts skipped for {a['id']}: {e_}")
        if i % 25 == 0 or i == len(areas):
            print(f"{i}/{len(areas)} areas, {time.time() - t0:,.0f} s")

    index = {
        "generated": pd.Timestamp.now().isoformat(timespec="seconds"),
        "lastDay": str(last_day.date()) if last_day is not None else None,
        "unit": UNIT,
        "enso": {str(k): v for k, v in D.enso_marks().items()},
        "areas": [{
            "id": a["id"], "name": a["name"], "level": a["level"], "parent": a["parent"],
            "children": a["children"], "bbox": bboxes.get(a["id"]), "hasGeo": a.get("hasGeo", False),
            "frames": a.get("frames", []), "events": a.get("events", False), "cells": a.get("cells", False),
            "recent": a.get("recent", False), "spots": a.get("spots", False), "land": a.get("land", False),
            "forecast": a.get("forecast", False),
            **({"empty": True} if a.get("empty") else {}),
        } for a in areas],
    }
    if args.countries and (out / "index.json").exists():  # keep the areas this run did not write
        index = merge_index(json.loads((out / "index.json").read_text(encoding="utf-8")), index)
    write_json(out / "index.json", index)
    if concessions and any(a.get("land") for a in areas):
        write_json(out / "land" / "_concessions.json", V.concessions_geojson(concessions))
    write_json(out / "asmc.json", V.asmc_block())
    write_json(out / "alerts.json", {
        "generated": pd.Timestamp.now().isoformat(timespec="seconds"),
        "lastDay": str(last_day.date()) if last_day is not None else None,
        "rules": {"surge": f">= {AL.SURGE_WATCH:g}x the usual fire in the last 7 days (warning >= {AL.SURGE_WARNING:g}x), "
                           f"at least {AL.MIN_FIRE_DAYS} fire days",
                  "forecast": f">= {AL.FORECAST_WATCH:.0%} chance of more than usual next week (warning >= "
                              f"{AL.FORECAST_WARNING:.0%}), only where the forecast passed its backtest",
                  "big_fire": f"fire burning in the last 3 days >= {AL.BIG_WATCH_KM2:g} km² (warning >= "
                              f"{AL.BIG_WARNING_KM2:g} km²) or >= {AL.GROWTH_P:.0%} chance to reach 10 km²"},
        "alerts": [x.to_dict() for x in AL.sort_alerts(AL.dedupe(alerts))],
    })
    print(f"alerts: {len(alerts)} ({sum(x.level == 'warning' for x in alerts)} warnings)")
    mb = {k: round(v / 1e6, 1) for k, v in sizes.items()}
    print(f"wrote {len(areas)} areas to {out} in {time.time() - t0:,.0f} s; MB: {mb}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
