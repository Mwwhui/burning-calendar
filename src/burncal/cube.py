"""Process FIRMS files one at a time into a small monthly "cube" (constant memory).

All of Asia is tens of millions of hotspots, too many to hold in RAM at once. Each raw
CSV is processed on its own:

    load -> drop NRT rows already covered by SP -> clean -> drop static sources
    -> local solar date
    -> tag country / adm1 / adm2 -> ~1 km cell-days -> monthly counts

and two Parquet files are written per input file:
    <out>/counts/<name>.parquet   monthly counts by satellite x region (tiny)
    <out>/points/<name>.parquet   cleaned, tagged hotspots (for CSV downloads in the app)
`cube.parquet` is the sum of all count files. Re-running only processes new or changed
input files (tracked in manifest.json), so new downloads are cheap to add.

Cell-days are de-duplicated within a file. FIRMS country files split hotspots by
country, so a ~1 km cell on a border can count once per country; this is negligible.
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np
import pandas as pd

from .aggregate import add_cells, add_solar_date
from .clean import clean
from .config import PLATFORMS, Settings
from .rawstore import load_raw
from .static import drop_static, load_mask, mask_id

log = logging.getLogger(__name__)

REGION_COLS = ["country", "adm1", "adm2"]
CUBE_KEYS = ["month", "satellite"] + REGION_COLS
POINT_COLS = ["latitude", "longitude", "acq_date", "acq_time", "solar_date", "satellite", "sensor",
              "product", "confidence", "frp", "daynight", "type"] + REGION_COLS


def raw_files(raw_dir: str | Path) -> list[Path]:
    """Raw FIRMS files under raw_dir (hidden folders skipped), SP before NRT: CSVs and slim Parquet files
    (burncal.rawstore). A CSV whose slim copy exists is skipped, so no file is counted twice."""
    raw_dir = Path(raw_dir)
    files = [p for p in list(raw_dir.rglob("*.csv")) + list(raw_dir.rglob("*.parquet"))
             if not any(part.startswith(".") for part in p.relative_to(raw_dir).parts)
             and not (p.suffix == ".csv" and p.with_suffix(".parquet").exists())]
    return sorted(files, key=lambda p: ("nrt" in p.name.lower(), str(p)))


def _file_id(path: Path, raw_dir: Path) -> str:
    return str(path.relative_to(raw_dir)).replace("\\", "/")


def summarize(hot: pd.DataFrame, grid_deg: float) -> pd.DataFrame:
    """Monthly cell-days, points and FRP sum per satellite x region for one cleaned, tagged file."""
    if hot.empty:
        return pd.DataFrame(columns=CUBE_KEYS + ["cell_days", "points", "frp_sum"])
    d = hot.copy()
    d["month"] = d["solar_date"].dt.to_period("M")
    for c in REGION_COLS:
        d[c] = d[c].fillna("")  # groupby drops NaN keys otherwise
    points = d.groupby(CUBE_KEYS).agg(points=("latitude", "size"), frp_sum=("frp", "sum"))
    cells = add_cells(d, grid_deg).drop_duplicates(["satellite", "cell_y", "cell_x", "solar_date"])
    cell_days = cells.groupby(CUBE_KEYS).size().rename("cell_days")
    out = points.join(cell_days, how="left").fillna({"cell_days": 0}).reset_index()
    out["cell_days"] = out["cell_days"].astype("int64")
    return out[CUBE_KEYS + ["cell_days", "points", "frp_sum"]]


def build_cube(raw_dir: str | Path, out_dir: str | Path, settings: Settings | None = None,
               tagger=None, write_points: bool = True, progress: bool = True) -> pd.DataFrame:
    """Process every raw file not yet in the manifest; write and return the combined cube."""
    from .io import drop_nrt_overlap
    from .regions import RegionTagger

    s = settings or Settings()
    raw_dir, out_dir = Path(raw_dir), Path(out_dir)
    (out_dir / "counts").mkdir(parents=True, exist_ok=True)
    if write_points:
        (out_dir / "points").mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {"files": {}}
    mask = load_mask(s.static_mask) if s.static_mask else None
    settings_key = f"{s.modis_min_confidence}|{','.join(s.viirs_keep_confidence)}|{s.keep_type}|{s.grid_deg}"
    if mask is not None:
        settings_key += f"|static={mask_id(mask)}"
    if manifest.get("settings_key") not in (None, settings_key):
        raise ValueError(f"{out_dir} was built with different cleaning settings; use a new out_dir")
    manifest["settings_key"] = settings_key
    tagger = tagger or RegionTagger(s.boundary_dir)

    files = raw_files(raw_dir)
    # last SP date per satellite, from files processed earlier and in this run
    sp_last: dict[str, str] = {}
    for meta in manifest["files"].values():
        for sat, last in meta.get("sp_last", {}).items():
            sp_last[sat] = max(sp_last.get(sat, last), last)

    todo = []
    for p in files:
        fid = _file_id(p, raw_dir)
        st = p.stat()
        meta = manifest["files"].get(fid)
        if not meta or meta["size"] != st.st_size or meta["mtime"] != int(st.st_mtime):
            todo.append(p)
    for i, p in enumerate(todo, 1):
        fid = _file_id(p, raw_dir)
        raw = load_raw(p)
        if raw is None:
            manifest["files"][fid] = {"size": p.stat().st_size, "mtime": int(p.stat().st_mtime), "skipped": True}
            continue
        n_raw = len(raw)
        if (raw["product"] == "NRT").any() and sp_last:
            fake_sp = pd.DataFrame({"satellite": list(sp_last), "acq_date": pd.to_datetime(list(sp_last.values())),
                                    "product": "SP"})
            raw = drop_nrt_overlap(pd.concat([raw, fake_sp], ignore_index=True))
            raw = raw[raw["latitude"].notna()]
        sp_rows = raw[raw["product"] == "SP"]
        file_sp_last = {sat: g.max().strftime("%Y-%m-%d") for sat, g in sp_rows.groupby("satellite")["acq_date"]}
        for sat, last in file_sp_last.items():
            sp_last[sat] = max(sp_last.get(sat, last), last)

        hot = clean(raw, s)
        n_clean = len(hot)
        hot = drop_static(hot, mask, s.grid_deg)
        hot = add_solar_date(hot)
        hot = tagger.tag(hot) if len(hot) else hot.assign(country=None, adm1=None, adm2=None)
        counts = summarize(hot, s.grid_deg)
        stem = fid.replace("/", "__").removesuffix(".csv").removesuffix(".parquet")
        counts.assign(month=counts["month"].astype(str)).to_parquet(out_dir / "counts" / f"{stem}.parquet", index=False)
        if write_points and len(hot):
            hot[POINT_COLS].to_parquet(out_dir / "points" / f"{stem}.parquet", index=False)
        manifest["files"][fid] = {"size": p.stat().st_size, "mtime": int(p.stat().st_mtime), "rows_raw": n_raw,
                                  "rows_clean": int(len(hot)),
                                  "rows_static": int(n_clean - len(hot)), "sp_last": file_sp_last, "counts": f"{stem}.parquet"}
        manifest_path.write_text(json.dumps(manifest, indent=1))
        if progress:
            print(f"\r{i}/{len(todo)} files processed ({fid}: {n_raw:,} -> {len(hot):,} rows)      ", end="", flush=True)
    if progress and todo:
        print()

    parts = [pd.read_parquet(out_dir / "counts" / m["counts"]) for m in manifest["files"].values() if "counts" in m]
    cube = pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=CUBE_KEYS + ["cell_days", "points", "frp_sum"])
    cube = cube.groupby(CUBE_KEYS, as_index=False)[["cell_days", "points", "frp_sum"]].sum()
    cube.to_parquet(out_dir / "cube.parquet", index=False)
    return load_cube(out_dir / "cube.parquet")


def load_cube(path: str | Path) -> pd.DataFrame:
    cube = pd.read_parquet(path)
    cube["month"] = pd.PeriodIndex(cube["month"].astype(str), freq="M")
    for c in REGION_COLS:
        cube[c] = cube[c].replace("", None)
    return cube


def platform_coverage(cube: pd.DataFrame, stub_share: float = 0.02) -> dict[str, tuple[str, str]]:
    """First and last month each satellite has data anywhere in the cube.

    Counting on local solar dates moves detections from late on the last UTC day of a
    file (e.g. 31 Dec) into the next month. That leaves a stub month of a few hours that
    is not real coverage, and would add a nonsense pair to the fits. An edge month with
    less than `stub_share` of its inner neighbour's total is therefore trimmed. A real
    partial month (e.g. the first 10 days of the current month) is far above that share.
    """
    out = {}
    for sat, g in cube.groupby("satellite"):
        tot = g.groupby("month")["points"].sum().sort_index()
        while len(tot) > 1 and tot.iloc[-1] < stub_share * tot.iloc[-2]:
            tot = tot.iloc[:-1]
        while len(tot) > 1 and tot.iloc[0] < stub_share * tot.iloc[1]:
            tot = tot.iloc[1:]
        out[sat] = (str(tot.index.min()), str(tot.index.max()))
    return out


def monthly_from_cube(cube: pd.DataFrame, countries=None, adm1=None, adm2=None,
                      unit: str = "cell_days") -> pd.DataFrame:
    """Monthly counts per satellite (columns) for a region, like aggregate.monthly_counts.

    countries: ISO3 code or list; None = all Asian countries (burncal.regions.ASIA_ISO3).
    Platform coverage comes from the whole cube, so a quiet region still gets 0 (not NaN)
    in months when the satellite was flying.
    """
    from .regions import as_isos

    col = {"cell_days": "cell_days", "points": "points"}[unit]
    countries = as_isos(countries)
    sel = cube["country"].isin(countries)
    if adm1:
        sel &= cube["adm1"].isin([adm1] if isinstance(adm1, str) else list(adm1))
    if adm2:
        sel &= cube["adm2"].isin([adm2] if isinstance(adm2, str) else list(adm2))
    part = cube[sel]
    full = pd.period_range(cube["month"].min(), cube["month"].max(), freq="M")
    wide = part.groupby(["month", "satellite"])[col].sum().unstack("satellite").reindex(full).astype(float)
    cov = platform_coverage(cube)
    for sat in cov:
        if sat not in wide:
            wide[sat] = np.nan
        lo, hi = pd.Period(cov[sat][0], "M"), pd.Period(cov[sat][1], "M")
        inside = (wide.index >= lo) & (wide.index <= hi)
        wide.loc[inside, sat] = wide.loc[inside, sat].fillna(0)
        wide.loc[~inside, sat] = np.nan
    wide = wide[[p for p in PLATFORMS if p in wide.columns]]
    wide.index.name = "month"
    wide.columns.name = None
    return wide


def apply_mask_to_store(out_dir: str | Path, mask_path: str | Path, grid_deg: float = 0.01,
                        progress: bool = True) -> pd.DataFrame:
    """Apply a larger static-source mask to an existing store without re-reading the raw files.

    Only valid when the new mask contains every cell of the mask the store was built with
    (e.g. after lowering the label threshold): then dropping the extra cells from the
    stored points and recounting gives exactly what a full rebuild would. The manifest's
    settings key is updated so later incremental builds use the new mask too.
    """
    from .static import drop_static, load_mask, mask_id

    out_dir = Path(out_dir)
    manifest_path = out_dir / "manifest.json"
    manifest = json.loads(manifest_path.read_text())
    mask = load_mask(mask_path)
    key = manifest.get("settings_key", "")
    if "|static=" not in key:
        raise ValueError("store was built without a static mask; rebuild it with the mask instead")
    files = [(fid, m) for fid, m in manifest["files"].items() if "counts" in m]
    for i, (fid, m) in enumerate(files, 1):
        stem = m["counts"].removesuffix(".parquet")
        pp = out_dir / "points" / f"{stem}.parquet"
        if not pp.exists():
            continue
        pts = pd.read_parquet(pp)
        kept = drop_static(pts, mask, grid_deg)
        if len(kept) < len(pts):
            kept.to_parquet(pp, index=False)
            counts = summarize(kept, grid_deg)
            counts.assign(month=counts["month"].astype(str)).to_parquet(out_dir / "counts" / m["counts"], index=False)
            m["rows_static"] = int(m.get("rows_static", 0) + len(pts) - len(kept))
            m["rows_clean"] = int(len(kept))
        if progress:
            print(f"\r{i}/{len(files)} files", end="", flush=True)
    if progress:
        print()
    manifest["settings_key"] = key.split("|static=")[0] + f"|static={mask_id(mask)}"
    manifest_path.write_text(json.dumps(manifest, indent=1))
    parts = [pd.read_parquet(out_dir / "counts" / m["counts"]) for _, m in files]
    cube = pd.concat(parts, ignore_index=True).groupby(CUBE_KEYS, as_index=False)[["cell_days", "points", "frp_sum"]].sum()
    cube.to_parquet(out_dir / "cube.parquet", index=False)
    return load_cube(out_dir / "cube.parquet")
