"""burncal.alerts: simple, checkable rules."""

import pandas as pd

from burncal.alerts import big_fire_alerts, forecast_alert, sort_alerts, surge_alert


def test_surge_needs_a_real_jump_and_enough_fire():
    w = {"total": 90.0, "median": 30.0, "rank": 1, "n_years": 26}
    a = surge_alert("mys", "Malaysia", w, "5 Nov", "11 Nov")
    assert a.level == "warning" and a.kind == "surge" and a.value == 3.0
    assert surge_alert("mys", "M", {**w, "total": 65.0}, "", "").level == "watch"  # 2.2x
    assert surge_alert("mys", "M", {**w, "total": 40.0}, "", "") is None       # 1.3x
    assert surge_alert("mys", "M", {**w, "total": 10.0, "median": 2.0}, "", "") is None  # tiny numbers
    assert surge_alert("mys", "M", None, "", "") is None


def test_forecast_only_when_usable_and_likely():
    fc = {"usable": True, "pAbove": 0.92, "q10": 20, "q50": 40, "q90": 70, "usual": 15}
    assert forecast_alert("x", "X", fc).level == "warning"
    assert forecast_alert("x", "X", {**fc, "pAbove": 0.8}).level == "watch"
    assert forecast_alert("x", "X", {**fc, "usable": False}) is None
    assert forecast_alert("x", "X", {**fc, "q50": 5}) is None


def test_big_fires_burning_now():
    last = pd.Timestamp("2026-11-11")
    ev = pd.DataFrame({
        "event_id": [1, 2, 3, 4], "start": pd.to_datetime(["2026-11-01", "2026-11-09", "2026-11-10", "2026-10-01"]),
        "end": pd.to_datetime(["2026-11-11", "2026-11-11", "2026-11-11", "2026-10-05"]), "days": [11, 3, 2, 5],
        "area_km2": [150.0, 30.0, 3.0, 500.0], "lat": [1.0] * 4, "lon": [110.0] * 4,
        "adm1": ["Sarawak"] * 4, "adm2": ["Miri"] * 4,
    })
    p = pd.Series({3: 0.7})
    out = big_fire_alerts("mys", "Malaysia", ev, last, p, growth_usable=True)
    assert [a.level for a in out] == ["warning", "watch", "watch"]  # 150 km², 30 km², likely to grow
    assert "likely to grow" in out[2].title
    assert len(big_fire_alerts("mys", "Malaysia", ev, last, p, growth_usable=False)) == 2  # event 4 ended


def test_warnings_first():
    a = surge_alert("a", "A", {"total": 50.0, "median": 20.0, "rank": 1, "n_years": 5}, "", "")
    b = surge_alert("b", "B", {"total": 90.0, "median": 20.0, "rank": 1, "n_years": 5}, "", "")
    assert [x.area_id for x in sort_alerts([a, b])] == ["b", "a"]


def test_telegram_selection_and_message():
    import importlib.util
    from pathlib import Path
    spec = importlib.util.spec_from_file_location("send_alerts", Path(__file__).resolve().parents[1] / "scripts" / "send_alerts.py")
    sa = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(sa)
    alerts = [{"areaId": "idn", "name": "Indonesia", "level": "warning", "kind": "surge", "title": "4.8x", "detail": "d"},
              {"areaId": "mys/sarawak", "name": "Sarawak", "level": "watch", "kind": "forecast", "title": "t", "detail": "d"}]
    assert [a["areaId"] for a in sa.select(alerts, [])] == ["idn"]          # default: warnings only
    assert [a["areaId"] for a in sa.select(alerts, ["mys"])] == ["mys/sarawak"]  # inside a watched country
    msg = sa.message({"lastDay": "2026-11-11"}, alerts)
    assert "Indonesia: 4.8x" in msg and "/mys/sarawak/" in msg


def test_one_fire_is_reported_once_under_the_most_specific_area():
    from burncal.alerts import dedupe
    last = pd.Timestamp("2026-11-11")
    ev = pd.DataFrame({"event_id": [7], "start": [pd.Timestamp("2026-11-01")], "end": [last], "days": [11],
                       "area_km2": [150.0], "lat": [-3.2], "lon": [112.1], "adm1": ["Central Kalimantan"], "adm2": [None]})
    a = big_fire_alerts("idn", "Indonesia", ev, last) + big_fire_alerts("idn/central-kalimantan", "Central Kalimantan", ev, last)
    out = dedupe(a)
    assert [x.area_id for x in out] == ["idn/central-kalimantan"]
    assert "3.200°S, 112.100°E" in out[0].detail
