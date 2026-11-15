"""Daily data update: newest NASA FIRMS detections -> rebuilt tables -> forecast -> web export.

Steps (each must succeed before the next starts; one run at a time):
  1. download   re-fetch the last week of NOAA-20 near-real-time (NRT) detections for the three
                Asia boxes and the Argentina box (the newest chunks are often incomplete when first downloaded)
  2. cube       scripts/build_cube.py (incremental: only changed files)
  3. daily      scripts/build_daily.py --no-detail (per-file cache: only changed files)
  4. events     scripts/build_events.py
  4b. growth    scripts/build_growth.py (fire-growth model, scores for recent fires; Asia and Americas apart)
  5. fine       scripts/build_fine_cells.py --years <current year> (+ the previous one in January)
  5b. weather   scripts/download_weather.py --refresh 30 (NASA POWER rain, heat, humidity, wind, soil)
  6. forecast   scripts/build_forecast.py (Asia) and --countries ARG into forecast_other (own model)
  7. export     scripts/export_web.py into web/public/data.next (+ scripts/build_event_dots.py: where each listed
                fire burned), then swapped in for web/public/data
  8. points     scripts/export_points.py --years <current year>: hotspot files for the CSV download
  9. notify     scripts/send_alerts.py: new alerts to Telegram, only if a bot is set up in .env

Status: data/processed/update_status.json and web/public/data/update.json (shown in the app).

    python scripts/update_daily.py                     # full update
    python scripts/update_daily.py --only download     # one step (also: --from forecast)
    python scripts/update_daily.py --raw <dir> --only download   # test the download elsewhere
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
from datetime import date, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
STEPS = ["download", "cube", "daily", "events", "growth", "fine", "weather", "forecast", "export", "points", "notify"]
BOXES = ["sea", "asia_west", "asia_north", "argentina"]
SOURCES = ["VIIRS_NOAA20_NRT"]
REFRESH_DAYS = 7
LOCK = ROOT / "data" / "processed" / ".update.lock"
STATUS = ROOT / "data" / "processed" / "update_status.json"
WEB_DATA = ROOT / "web" / "public" / "data"


def log(msg: str) -> None:
    print(f"[{datetime.now():%Y-%m-%d %H:%M:%S}] {msg}", flush=True)


def run(args: list[str]) -> None:
    log("run: " + " ".join(args))
    r = subprocess.run([PY, *args], cwd=ROOT)
    if r.returncode != 0:
        raise RuntimeError(f"{args[0]} failed with exit code {r.returncode}")


def step_download(raw: Path, today: date, since: date | None = None) -> None:
    sys.path.insert(0, str(ROOT / "scripts"))
    import download_firms as DF

    for box in BOXES:
        bbox = DF.BBOX_PRESETS[box]
        for source in SOURCES:
            cache = raw / ".cache" / DF.bbox_tag(bbox) / source
            if cache.exists():  # the newest chunks may have been incomplete: fetch them again
                for f in cache.glob("*.csv"):
                    if date.fromisoformat(f.name[:10]) >= today - timedelta(days=REFRESH_DAYS):
                        f.unlink()
            # FIRMS clamps the start to what NRT covers, so only missing chunks are fetched
            start = since or date(today.year - 1, 12, 1)
            DF.main(["--source", source, "--bbox", box, "--start", start.isoformat(),
                     "--end", today.isoformat(), "--out", str(raw)])


def step_export() -> None:
    nxt = WEB_DATA.with_name("data.next")
    if nxt.exists():
        shutil.rmtree(nxt)
    run(["scripts/export_web.py", "--out", str(nxt)])
    run(["scripts/build_event_dots.py", "--data", str(nxt)])
    prev = WEB_DATA.with_name("data.prev")
    if prev.exists():
        shutil.rmtree(prev)
    if WEB_DATA.exists():
        WEB_DATA.rename(prev)
    nxt.rename(WEB_DATA)
    log(f"swapped the new export into {WEB_DATA} (previous one kept in {prev.name})")


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", choices=STEPS)
    ap.add_argument("--from", dest="start", choices=STEPS, help="start at this step")
    ap.add_argument("--raw", type=Path, default=ROOT / "data" / "raw", help="raw download folder")
    ap.add_argument("--since", type=date.fromisoformat, help="download from this date only (tests)")
    args = ap.parse_args(argv)
    steps = [args.only] if args.only else STEPS[STEPS.index(args.start):] if args.start else STEPS
    today = date.today()

    test = args.raw.resolve() != (ROOT / "data" / "raw").resolve()
    if test and steps != ["download"]:
        log("--raw elsewhere is only for testing the download step (use --only download)")
        return 2
    if not test and LOCK.exists() and time.time() - LOCK.stat().st_mtime < 8 * 3600:
        log(f"another update is running (lock {LOCK}); stopping")
        return 1
    if not test:
        LOCK.parent.mkdir(parents=True, exist_ok=True)
        LOCK.write_text(str(datetime.now()))
    status = {"started": datetime.now().isoformat(timespec="seconds"), "steps": {}, "ok": False}
    try:
        for s in steps:
            t0 = time.time()
            log(f"== {s}")
            if s == "download":
                step_download(args.raw, today, args.since)
            elif s == "cube":
                run(["scripts/build_cube.py"])
            elif s == "daily":
                run(["scripts/build_daily.py", "--no-detail"])
            elif s == "events":
                run(["scripts/build_events.py"])
            elif s == "growth":
                run(["scripts/build_growth.py"])
                run(["scripts/build_growth.py", "--region", "americas", "--out", "data/processed/growth_other"])
            elif s == "fine":
                years = sorted({today.year, (today - timedelta(days=60)).year})
                run(["scripts/build_fine_cells.py", "--years", *map(str, years)])
            elif s == "weather":  # NASA POWER, last 30 days re-fetched (values can be revised)
                run(["scripts/download_weather.py", "--refresh", "30"])
            elif s == "forecast":
                run(["scripts/build_forecast.py"])
                run(["scripts/build_forecast.py", "--countries", "ARG", "--out", "data/processed/forecast_other"])
            elif s == "export":
                step_export()
            elif s == "notify":  # Telegram, only if configured in .env (scripts/send_alerts.py)
                run(["scripts/send_alerts.py"])
            elif s == "points":  # hotspot CSV files for the browser (web/public/detections)
                years = sorted({today.year, (today - timedelta(days=7)).year})
                run(["scripts/export_points.py", "--years", *map(str, years)])
            status["steps"][s] = round(time.time() - t0)
        status["ok"] = True
    except Exception as e:  # noqa: BLE001
        status["error"] = str(e)
        log(f"FAILED: {e}")
    finally:
        status["finished"] = datetime.now().isoformat(timespec="seconds")
        try:
            idx = json.loads((WEB_DATA / "index.json").read_text(encoding="utf-8"))
            status["lastDay"] = idx.get("lastDay")
        except Exception:  # noqa: BLE001
            pass
        if not test:
            STATUS.write_text(json.dumps(status, indent=1), encoding="utf-8")
            if WEB_DATA.exists():
                (WEB_DATA / "update.json").write_text(json.dumps(status), encoding="utf-8")
            LOCK.unlink(missing_ok=True)
    log("done" if status["ok"] else "stopped with an error")
    return 0 if status["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
