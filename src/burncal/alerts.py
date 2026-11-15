"""Fire alerts: plain rules on numbers the app already computes, re-run with every data update.

Rules (each gives a level, "watch" or "warning"):

    surge      the last 7 days had far more fire than the same 7 days in other years
               (harmonized window total, burncal.daily.window_totals; median of the other years):
               >= 2x the median -> watch, >= 3x -> warning; only when the 7 days have >= MIN_FIRE_DAYS
               and the median is >= 3 (a jump from 0 to 4 fires is not a surge)
    forecast   the next-7-days forecast is usable (beat simple forecasts in the backtest) and gives
               >= 75 % chance of more than usual, with a most likely value >= MIN_FIRE_DAYS -> watch
               (>= 90 % -> warning)
    big_fire   a fire burning in the last 3 days is already >= 25 km², or the fire-growth model
               gives it >= 50 % chance to reach 10 km² (only when that model is usable) -> watch;
               >= 100 km² -> warning

The thresholds are deliberately simple so a user can check every alert against the app.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass

import numpy as np
import pandas as pd

MIN_FIRE_DAYS = 20
SURGE_WATCH, SURGE_WARNING = 2.0, 3.0
FORECAST_WATCH, FORECAST_WARNING = 0.75, 0.90
BIG_WATCH_KM2, BIG_WARNING_KM2 = 25.0, 100.0
GROWTH_P = 0.5


@dataclass
class Alert:
    area_id: str
    name: str
    level: str  # "watch" | "warning"
    kind: str  # "surge" | "forecast" | "big_fire"
    title: str
    detail: str
    value: float | None = None
    # the same thing seen from several areas (e.g. one fire in a country, its state and district)
    key: str | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["areaId"] = d.pop("area_id")
        d.pop("key")
        return d


def _latlon(lat: float, lon: float) -> str:
    return f"{abs(lat):.3f}°{'N' if lat >= 0 else 'S'}, {abs(lon):.3f}°{'E' if lon >= 0 else 'W'}"


def dedupe(alerts: list[Alert]) -> list[Alert]:
    """Keep each keyed alert once, under the most specific area (longest id)."""
    best: dict[str, Alert] = {}
    out = []
    for a in alerts:
        if a.key is None:
            out.append(a)
        elif a.key not in best or len(a.area_id) > len(best[a.key].area_id):
            best[a.key] = a
    return out + list(best.values())


def surge_alert(area_id: str, name: str, window: dict | None, start: str, end: str) -> Alert | None:
    """`window`: burncal.daily.compare_window output for the last 7 days."""
    if not window:
        return None
    total, med = window.get("total"), window.get("median")
    if total is None or med is None or not np.isfinite(med) or med < 3 or total < MIN_FIRE_DAYS:
        return None
    ratio = total / med
    if ratio < SURGE_WATCH:
        return None
    level = "warning" if ratio >= SURGE_WARNING else "watch"
    return Alert(area_id, name, level, "surge",
                 f"{ratio:.1f}× the usual fire in the last 7 days",
                 f"{total:,.0f} fire days {start} – {end}; usually about {med:,.0f} on these dates "
                 f"(rank #{window.get('rank')} of {window.get('n_years')}).", round(float(ratio), 2))


def forecast_alert(area_id: str, name: str, fc: dict | None) -> Alert | None:
    """`fc`: the 'h1' horizon of the exported forecast block."""
    if not fc or not fc.get("usable"):
        return None
    p, q50 = fc.get("pAbove"), fc.get("q50")
    if p is None or q50 is None or p < FORECAST_WATCH or q50 < MIN_FIRE_DAYS:
        return None
    level = "warning" if p >= FORECAST_WARNING else "watch"
    return Alert(area_id, name, level, "forecast", f"{p:.0%} chance of more fire than usual next week",
                 f"Forecast {fc.get('q10'):,.0f}–{fc.get('q90'):,.0f} fire days (most likely {q50:,.0f}); "
                 f"usual about {fc.get('usual') or 0:,.0f}.", round(float(p), 2))


def big_fire_alerts(area_id: str, name: str, events: pd.DataFrame, last_day: pd.Timestamp,
                    p_big: pd.Series | None = None, growth_usable: bool = False, max_n: int = 3) -> list[Alert]:
    """Fires burning in the last 3 days that are already big, or likely to become big."""
    if events is None or events.empty:
        return []
    recent = events[pd.to_datetime(events["end"]) >= pd.Timestamp(last_day) - pd.Timedelta(days=2)]
    out = []
    for _, e in recent.sort_values("area_km2", ascending=False).iterrows():
        km2 = float(e["area_km2"])
        p = float(p_big.get(int(e["event_id"]), np.nan)) if p_big is not None else np.nan
        likely = growth_usable and np.isfinite(p) and p >= GROWTH_P and km2 < BIG_WATCH_KM2
        if km2 < BIG_WATCH_KM2 and not likely:
            continue
        level = "warning" if km2 >= BIG_WARNING_KM2 else "watch"
        where = ", ".join(x for x in (e.get("adm2"), e.get("adm1")) if isinstance(x, str) and x) or name
        if likely:
            title = f"New fire likely to grow ({p:.0%} chance of 10 km² or more)"
        else:
            title = f"Large fire burning: {km2:,.0f} km²"
        out.append(Alert(area_id, name, level, "big_fire", title,
                         f"{where}, burning since {pd.Timestamp(e['start']):%d %b} "
                         f"({int(e['days'])} days); centre {_latlon(float(e['lat']), float(e['lon']))}.", round(km2, 1),
                         key=f"fire:{int(e['event_id'])}"))
        if len(out) >= max_n:
            break
    return out


LEVEL_ORDER = {"warning": 0, "watch": 1}


def sort_alerts(alerts: list[Alert]) -> list[Alert]:
    return sorted(alerts, key=lambda a: (LEVEL_ORDER.get(a.level, 9), -(a.value or 0)))
