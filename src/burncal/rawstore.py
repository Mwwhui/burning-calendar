"""Slim raw store: FIRMS CSVs kept as compressed Parquet in the standard schema.

Raw FIRMS CSVs are large (all of Asia: 8.8 GB for ~85 M detections). The pipeline only ever reads them
through `io.standardize`, so each CSV can be replaced by a Parquet file holding exactly the standardized
table (STANDARD_COLUMNS, same values), written next to it with the same name and a `.parquet` suffix.
That is several times smaller, faster to read, and lets the whole world fit on a small disk:

    download -> slim_file() -> CSV deleted -> cube / static mask / rebuilds read the Parquet file

`load_raw` reads either form and returns the same table, so `build_cube` gives identical counts.
`migrate_manifest` renames a processed CSV's manifest entry to its Parquet file, so the cube does not
count the file twice.
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .io import STANDARD_COLUMNS, load_firms_csv

SLIM = ".parquet"
# text columns stored as categories (small on disk and in memory); restored to plain strings on read
_TEXT = ["satellite", "sensor", "product", "confidence", "daynight"]


def slim_path(csv_path: str | Path) -> Path:
    return Path(csv_path).with_suffix(SLIM)


def _restore(df: pd.DataFrame) -> pd.DataFrame:
    """Same dtypes as io.standardize returns (object text, float/datetime numbers)."""
    for c in _TEXT:
        if c in df and df[c].dtype.name == "category":
            df[c] = df[c].astype(object)
    return df[STANDARD_COLUMNS]


def load_raw(path: str | Path) -> pd.DataFrame | None:
    """A raw FIRMS file (CSV or slim Parquet) in the standard schema; None if it is not a FIRMS table."""
    path = Path(path)
    if path.suffix.lower() == SLIM:
        return _restore(pd.read_parquet(path))
    return load_firms_csv(path)


def slim_file(csv_path: str | Path, delete_csv: bool = True) -> Path | None:
    """Write the CSV's standardized table as Parquet next to it, check it reads back identically, and
    (by default) delete the CSV. Returns the Parquet path, or None (CSV kept) if it is not a FIRMS table."""
    csv_path = Path(csv_path)
    std = load_firms_csv(csv_path)
    if std is None:
        return None
    out = slim_path(csv_path)
    slim = std.copy()
    for c in _TEXT:
        if slim[c].notna().any():
            slim[c] = slim[c].astype("category")
    tmp = out.with_suffix(".tmp")
    slim.to_parquet(tmp, index=False, compression="zstd")
    back = load_raw(tmp.rename(out))
    pd.testing.assert_frame_equal(back.reset_index(drop=True), std.reset_index(drop=True), check_dtype=False)
    if delete_csv:
        csv_path.unlink()
    return out


def migrate_manifest(out_dir: str | Path, raw_dir: str | Path, csv_path: str | Path) -> bool:
    """Point a processed CSV's manifest entry (build_cube) at its slim Parquet file. True if an entry moved."""
    out_dir, raw_dir = Path(out_dir), Path(raw_dir)
    mp = out_dir / "manifest.json"
    if not mp.exists():
        return False
    manifest = json.loads(mp.read_text())
    old = str(Path(csv_path).relative_to(raw_dir)).replace("\\", "/")
    meta = manifest["files"].pop(old, None)
    if meta is None:
        return False
    new = slim_path(csv_path)
    st = new.stat()
    meta.update(size=st.st_size, mtime=int(st.st_mtime))
    manifest["files"][str(new.relative_to(raw_dir)).replace("\\", "/")] = meta
    mp.write_text(json.dumps(manifest, indent=1))
    return True
