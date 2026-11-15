"""Fire events: group detections into individual fires and compare a current fire with past ones.

The challenge asks "how a current fire compares with previous ones". A calendar counts
fire days; an event is one fire that spreads and lasts. Grouping rule (like NASA's Fire
Events Data Suite, FEDS, which links detections within 5 days so short gaps from clouds
or missed overpasses do not split a fire):

    two ~1 km cell-days belong to the same event if the cells touch (the same cell or
    one of its 8 neighbours) and their dates are at most `gap_days` apart (default 5).

Only one satellite is used (NOAA-20, the reference, from April 2018), so every event,
old or new, is measured with the same sensor and the same overpass time; no conversion is
needed. Limits: fires that burn side by side in a farming landscape merge into one event;
a fire seen only under cloud breaks may split.

Event table (one row per event): start, end, days, cell_days, area_km2 (area of the ~1 km
squares with detections; an upper bound of the burnt area, not a burnt-area map),
frp_max, centre lat/lon, bounding box, country/adm1/adm2 of most detections, peat share.
"""

from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

GRID_DEG = 0.01
KEY = 1_000_000  # cell key = gy * KEY + gx
DAY0 = pd.Timestamp("2000-01-01")
EVENT_SATELLITE = "NOAA20"
EVENT_COLS = ["event_id", "start", "end", "days", "cell_days", "cells", "area_km2", "frp_max", "frp_sum",
              "lat", "lon", "west", "south", "east", "north", "country", "adm1", "adm2", "peat_share",
              "early_cells", "early_cell_days", "early_days", "early_frp_sum", "early_frp_max", "early_peat",
              "early_extent_km", "early_area_km2"]
# What an event looked like in its first EARLY_DAYS days (days 0..EARLY_DAYS-1 from its start):
# the information a fire-growth model may use when it is issued at the end of day EARLY_DAYS - 1.
EARLY_DAYS = 3


def cell_days(points: pd.DataFrame, grid_deg: float = GRID_DEG) -> pd.DataFrame:
    """One row per ~1 km cell and local solar date, with max/summed FRP and region of the first point."""
    d = points.copy()
    d["gy"] = np.floor(d["latitude"].to_numpy(float) / grid_deg).astype("int64")
    d["gx"] = np.floor(d["longitude"].to_numpy(float) / grid_deg).astype("int64")
    d["day"] = (pd.to_datetime(d["solar_date"]) - DAY0).dt.days.astype("int64")
    for c in ("country", "adm1", "adm2"):
        if c not in d:
            d[c] = None
    if "peat" not in d:
        d["peat"] = False
    g = d.groupby(["gy", "gx", "day"], sort=False)
    out = g.agg(frp_max=("frp", "max"), frp_sum=("frp", "sum"), country=("country", "first"),
                adm1=("adm1", "first"), adm2=("adm2", "first"), peat=("peat", "first")).reset_index()
    return out


def link(cd: pd.DataFrame, gap_days: int = 5) -> np.ndarray:
    """Event label for each cell-day (connected components of the touch-and-gap rule)."""
    from scipy.sparse import coo_matrix
    from scipy.sparse.csgraph import connected_components

    n = len(cd)
    if n == 0:
        return np.zeros(0, "int64")
    key = cd["gy"].to_numpy("int64") * KEY + cd["gx"].to_numpy("int64")
    day = cd["day"].to_numpy("int64")
    code = key * 100_000 + day
    order = np.argsort(code)
    sorted_code = code[order]
    rows, cols = [], []
    # half of the neighbourhood is enough (links are undirected)
    offsets = [(0, 0)] + [(0, 1), (1, -1), (1, 0), (1, 1)]
    for dy, dx in offsets:
        for dt in range(-gap_days, gap_days + 1):
            if (dy, dx) == (0, 0) and dt <= 0:
                continue
            target = (key + dy * KEY + dx) * 100_000 + day + dt
            pos = np.searchsorted(sorted_code, target)
            pos = np.minimum(pos, n - 1)
            hit = sorted_code[pos] == target
            if hit.any():
                rows.append(np.nonzero(hit)[0])
                cols.append(order[pos[hit]])
    if rows:
        r, c = np.concatenate(rows), np.concatenate(cols)
    else:
        r = c = np.zeros(0, "int64")
    g = coo_matrix((np.ones(len(r), "int8"), (r, c)), shape=(n, n))
    _, labels = connected_components(g, directed=False)
    return labels.astype("int64")


def summarize_events(cd: pd.DataFrame, labels: np.ndarray, grid_deg: float = GRID_DEG) -> pd.DataFrame:
    d = cd.assign(event=labels)
    d["lat"] = (d["gy"] + 0.5) * grid_deg
    d["lon"] = (d["gx"] + 0.5) * grid_deg
    d["km2"] = (111.32 * grid_deg) ** 2 * np.cos(np.radians(d["lat"]))
    g = d.groupby("event")
    cells = d.drop_duplicates(["event", "gy", "gx"]).groupby("event")
    ev = pd.DataFrame({
        "start": DAY0 + pd.to_timedelta(g["day"].min(), unit="D"),
        "end": DAY0 + pd.to_timedelta(g["day"].max(), unit="D"),
        "cell_days": g.size(),
        "cells": cells.size(),
        "area_km2": cells["km2"].sum(),
        "frp_max": g["frp_max"].max(),
        "frp_sum": g["frp_sum"].sum(),
        "lat": g["lat"].mean(), "lon": g["lon"].mean(),
        "west": g["lon"].min() - grid_deg / 2, "east": g["lon"].max() + grid_deg / 2,
        "south": g["lat"].min() - grid_deg / 2, "north": g["lat"].max() + grid_deg / 2,
        "peat_share": g["peat"].mean(),
    })
    ev["days"] = (ev["end"] - ev["start"]).dt.days + 1
    # first EARLY_DAYS days of each event (burncal.growth uses only these)
    rel = d["day"].to_numpy() - g["day"].transform("min").to_numpy()
    e = d[rel < EARLY_DAYS]
    ge = e.groupby("event")
    ecells = e.drop_duplicates(["event", "gy", "gx"]).groupby("event")
    early = pd.DataFrame({
        "early_cells": ecells.size(),
        "early_cell_days": ge.size(),
        "early_days": ge["day"].nunique(),
        "early_frp_sum": ge["frp_sum"].sum(),
        "early_frp_max": ge["frp_max"].max(),
        "early_peat": ge["peat"].mean(),
        "early_area_km2": ecells["km2"].sum(),
        # diagonal of the box around the early cells, km
        "early_extent_km": np.hypot((ge["lat"].max() - ge["lat"].min() + grid_deg) * 111.32,
                                    (ge["lon"].max() - ge["lon"].min() + grid_deg) * 111.32
                                    * np.cos(np.radians(ge["lat"].mean()))),
    })
    ev = ev.join(early)
    # region (country/adm1/adm2 together) of most cell-days, vectorised
    reg = d[["event", "country", "adm1", "adm2"]].astype({"country": object, "adm1": object, "adm2": object})
    reg = reg.fillna({"country": "", "adm1": "", "adm2": ""})
    cnt = reg.groupby(["event", "country", "adm1", "adm2"], sort=False).size().rename("n").reset_index()
    top = cnt.sort_values(["event", "n"], ascending=[True, False]).drop_duplicates("event").set_index("event")
    for c in ("country", "adm1", "adm2"):
        ev[c] = top[c].reindex(ev.index).replace("", None)
    ev = ev.sort_values(["start", "lat"]).reset_index(drop=True)
    ev.insert(0, "event_id", np.arange(len(ev), dtype="int64"))
    return ev[EVENT_COLS]


def find_events(points: pd.DataFrame, gap_days: int = 5, grid_deg: float = GRID_DEG) -> pd.DataFrame:
    """Events from detections of ONE satellite (lat, lon, solar_date, frp, regions, optional peat)."""
    cd = cell_days(points, grid_deg)
    return summarize_events(cd, link(cd, gap_days), grid_deg)


def build_events(points_dir: str | Path, out: str | Path, satellite: str = EVENT_SATELLITE,
                 peat_cells: pd.DataFrame | None = None, gap_days: int = 5, progress: bool = True) -> pd.DataFrame:
    """Events for all of the store's detections from `satellite`; written to `out` (Parquet).

    Built one country at a time (all of Asia has ~30 M NOAA-20 detections, too many to link at
    once on a 16 GB machine). A fire that crosses a border is therefore split into one event
    per country; detections outside every country (sea, gas platforms) are left out."""
    import pyarrow as pa
    import pyarrow.compute as pc
    import pyarrow.dataset as ds

    cols = ["latitude", "longitude", "solar_date", "satellite", "frp", "country", "adm1", "adm2"]
    types = {"latitude": pa.float64(), "longitude": pa.float64(), "solar_date": pa.timestamp("ns"),
             "satellite": pa.string(), "frp": pa.float64(), "country": pa.string(), "adm1": pa.string(),
             "adm2": pa.string()}
    dset = ds.dataset(str(points_dir), format="parquet", schema=pa.schema([(c, types[c]) for c in cols]))
    sat = pc.field("satellite") == satellite
    countries = pc.unique(dset.to_table(columns=["country"], filter=sat).column("country")).to_pylist()
    parts = []
    for i, c in enumerate(sorted(x for x in countries if x and x != "Other"), 1):
        pts = dset.to_table(filter=sat & (pc.field("country") == c)).to_pandas()
        for k in ("country", "adm1", "adm2"):
            pts[k] = pts[k].astype(object)
        if peat_cells is not None:
            from .peat import on_peat
            pts["peat"] = on_peat(pts["latitude"], pts["longitude"], peat_cells, GRID_DEG)
        parts.append(find_events(pts, gap_days))
        if progress:
            print(f"\r{i}/{len(countries)} countries ({c}: {len(pts):,} detections)", end="", flush=True)
        del pts
    if progress:
        print()
    ev = pd.concat(parts, ignore_index=True).sort_values(["start", "lat"]).reset_index(drop=True)
    ev["event_id"] = np.arange(len(ev), dtype="int64")
    ev = ev[EVENT_COLS]
    ev.to_parquet(out, index=False)
    return ev


def event_cell_days(cd: pd.DataFrame, event: pd.Series | dict, gap_days: int = 5,
                    grid_deg: float = GRID_DEG) -> pd.DataFrame:
    """The cell-days (output of `cell_days`, one country) that make up one event of the table.

    Events are not stored cell by cell, so they are found again: the cell-days inside the event's
    box and dates are linked with the same rule, and the group that starts on the event's first day
    with its number of cell-days is the event. Exact: every link of the event lies inside its box and
    dates, and anything linked to it would have widened them. Empty if not found (table out of date).
    """
    d0 = int((pd.Timestamp(event["start"]) - DAY0).days)
    d1 = int((pd.Timestamp(event["end"]) - DAY0).days)
    gx0, gx1 = round(event["west"] / grid_deg), round(event["east"] / grid_deg) - 1
    gy0, gy1 = round(event["south"] / grid_deg), round(event["north"] / grid_deg) - 1
    sub = cd[cd["day"].between(d0, d1) & cd["gx"].between(gx0, gx1) & cd["gy"].between(gy0, gy1)]
    if sub.empty:
        return sub
    lab = link(sub, gap_days)
    s = sub.assign(_e=lab)
    g = s.groupby("_e")["day"].agg(["min", "size"])
    hit = g[(g["min"] == d0) & (g["size"] == int(event["cell_days"]))]
    if hit.empty:
        return sub.iloc[0:0]
    return s[s["_e"] == hit["size"].idxmax()].drop(columns="_e")


def dots_json(cells: pd.DataFrame, event_id: int, start, grid_deg: float = GRID_DEG) -> dict:
    """Compact web form of an event's cell-days: offsets from the south-west cell and the first day.
    lon = (gx0 + gx + 0.5) * grid, lat = (gy0 + gy + 0.5) * grid, date = start + d days."""
    c = cells.sort_values(["day", "gy", "gx"])
    gx0, gy0 = int(c["gx"].min()), int(c["gy"].min())
    d0 = int(c["day"].min())
    return {
        "id": int(event_id), "start": str(pd.Timestamp(start).date()), "grid": grid_deg, "gx0": gx0, "gy0": gy0,
        "gx": (c["gx"] - gx0).astype(int).tolist(), "gy": (c["gy"] - gy0).astype(int).tolist(),
        "d": (c["day"] - d0).astype(int).tolist(),
        "frp": [int(round(v)) for v in c["frp_max"].fillna(0).to_numpy()],
    }


# ----------------------------------------------------------------------------- comparing
def compare_event(event: pd.Series, history: pd.DataFrame, measure: str = "area_km2") -> dict:
    """How one event ranks among all events in `history` (same area, same satellite).

    share_smaller: share of past events smaller than this one; bigger_before: the most
    recent earlier event that was bigger (None = biggest on record); n: events compared.
    """
    past = history[(history["event_id"] != event["event_id"]) & (history["start"] < event["start"])]
    v = float(event[measure])
    bigger = past[past[measure] > v]
    return {
        "n": int(len(past)),
        "share_smaller": float((past[measure] < v).mean()) if len(past) else float("nan"),
        "rank": int(len(bigger)) + 1,
        "bigger_before": bigger.sort_values("start").iloc[-1] if len(bigger) else None,
        "first": history["start"].min(),
    }


def active_events(events: pd.DataFrame, last_day, within_days: int = 5) -> pd.DataFrame:
    """Events with a detection in the last `within_days` days up to `last_day` (still burning)."""
    last_day = pd.Timestamp(last_day)
    return events[events["end"] > last_day - pd.Timedelta(days=within_days)]


def load_events(path: str | Path, columns: list[str] | None = None, compact: bool = False) -> pd.DataFrame:
    """Events table. `columns`: read only these; `compact`: region names as categories (several times
    less memory for millions of events; values and comparisons are unchanged)."""
    ev = pd.read_parquet(path, columns=columns)
    for c in ("start", "end"):
        if c in ev:
            ev[c] = pd.to_datetime(ev[c])
    if compact:
        for c in ("country", "adm1", "adm2"):
            if c in ev:
                ev[c] = ev[c].astype(object).astype("category")
    return ev
