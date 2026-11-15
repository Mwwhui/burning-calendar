"""scripts/export_web.py: ids, rounding and the area tree (synthetic data, no files)."""

import importlib.util
import math
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("export_web", ROOT / "scripts" / "export_web.py")
ew = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ew)


def test_slug_is_ascii_and_url_safe():
    assert ew.slug("Wilayah Persekutuan Kuala Lumpur") == "wilayah-persekutuan-kuala-lumpur"
    assert ew.slug("Bà Rịa–Vũng Tàu") == "ba-ria-vung-tau"
    assert ew.slug("???") == "area"


def test_num_is_json_safe():
    assert ew.num(1.234, 1) == 1.2
    assert ew.num(math.nan) is None
    assert ew.num(math.inf) is None
    assert ew.num(None) is None


def test_file_id_of_root():
    assert ew.file_id("") == "_all"
    assert ew.file_id("mys/sarawak") == "mys/sarawak"


def test_tree_links_parents_and_children():
    cube = pd.DataFrame({
        "month": ["2020-01"] * 4, "satellite": ["NOAA20"] * 4,
        "country": ["MYS", "MYS", "MYS", "IDN"],
        "adm1": ["Sarawak", "Sarawak", "Sabah", "Riau"],
        "adm2": ["Miri", "Kuching", None, None],
        "cell_days": [5, 3, 2, 9], "points": [5, 3, 2, 9], "frp_sum": [1.0] * 4,
    })
    areas = ew.build_tree(cube, None)
    by = {a["id"]: a for a in areas}
    assert by[""]["children"] == ["southeast-asia"]
    assert set(by["southeast-asia"]["children"]) == {"mys", "idn"}
    assert by["mys"]["children"] == ["mys/sarawak", "mys/sabah"]  # busiest first
    assert by["mys/sarawak"]["children"] == ["mys/sarawak/miri", "mys/sarawak/kuching"]
    assert by["mys/sarawak/miri"]["query"] == ["MYS", "Sarawak", "Miri"]
    assert all(by[c]["parent"] == a["id"] for a in areas for c in a["children"])
    only = {a["id"] for a in ew.build_tree(cube, {"MYS"})}
    assert "idn" not in only and "mys" in only


def test_countries_outside_asia_are_top_level():
    cube = pd.DataFrame({
        "month": ["2020-01"] * 3, "satellite": ["NOAA20"] * 3,
        "country": ["MYS", "ARG", "CHL"], "adm1": ["Sabah", "Entre Ríos", None], "adm2": [None] * 3,
        "cell_days": [2, 9, 4], "points": [2, 9, 4], "frp_sum": [1.0] * 3,
    })
    by = {a["id"]: a for a in ew.build_tree(cube, None)}
    assert by["arg"]["parent"] is None
    assert "arg" not in by[""]["children"] and "arg" not in by["southeast-asia"]["children"]
    assert by["arg"]["children"] == ["arg/entre-rios"]
    assert "chl" not in by  # neighbours caught by the download box are not study areas


def test_partial_export_keeps_other_areas_in_index():
    old = {"areas": [{"id": "", "children": ["southeast-asia"]}, {"id": "southeast-asia", "children": ["mys", "idn"]},
                     {"id": "mys", "children": [], "v": 1}, {"id": "idn", "children": []}, {"id": "arg", "children": ["arg/x"]}]}
    new = {"lastDay": "2026-11-14", "areas": [{"id": "", "children": ["southeast-asia"]},
                                              {"id": "southeast-asia", "children": ["mys"]}, {"id": "mys", "children": [], "v": 2}]}
    m = ew.merge_index(old, new)
    by = {a["id"]: a for a in m["areas"]}
    assert m["lastDay"] == "2026-11-14" and by["mys"]["v"] == 2 and "idn" in by and "arg" in by
    assert by["southeast-asia"]["children"] == ["mys", "idn"]


def test_index_entries_from_disk(tmp_path):
    areas = [{"id": "arg", "name": "Argentina", "level": "country", "parent": None, "children": ["arg/x"], "iso": "ARG"},
             {"id": "arg/x", "name": "X", "level": "adm1", "parent": "arg", "children": [], "iso": "ARG"},
             {"id": "arg/y", "name": "Y", "level": "adm1", "parent": "arg", "children": [], "iso": "ARG"}]
    ew.write_json(tmp_path / "geo" / "arg.json", {"type": "FeatureCollection", "features": [
        {"type": "Feature", "id": "arg/x", "properties": {"id": "arg/x"},
         "geometry": {"type": "Polygon", "coordinates": [[[-60, -30], [-58, -30], [-58, -28], [-60, -30]]]}}]})
    for d in ("area/arg", "area/arg/x", "frames/arg.year"):
        ew.write_json(tmp_path / f"{d}.json", {})
    ew.write_json(tmp_path / "cells" / "arg.json", {})
    by = {e["id"]: e for e in ew.index_entries_from_disk(areas, tmp_path)}
    assert by["arg/x"]["bbox"] == [-60, -30, -58, -28] and by["arg"]["bbox"] == [-60, -30, -58, -28]
    assert by["arg"]["hasGeo"] and by["arg"]["frames"] == ["year"] and by["arg"]["cells"] and by["arg"]["parent"] is None
    assert by["arg/y"].get("empty") and not by["arg/x"].get("empty")


def test_asia_map_links_countries_not_regions(monkeypatch):
    sq = {"type": "Polygon", "coordinates": [[[100, 0], [101, 0], [101, 1], [100, 0]]]}
    fake = {"geojson": {"type": "FeatureCollection", "features": [{"type": "Feature", "id": "MYS", "geometry": sq},
                                                                  {"type": "Feature", "id": "RUS", "geometry": sq}]},
            "names": {"MYS": "Malaysia", "RUS": "Russia"}, "km2": {"MYS": 1, "RUS": 1},
            "bounds": {"MYS": (100, 0, 101, 1), "RUS": (100, 0, 101, 1)}}
    monkeypatch.setattr(ew.D, "load_areas", lambda *a, **k: fake)
    areas = [{"id": "", "name": "Asia", "level": "asia", "parent": None, "children": ["southeast-asia", "rus"], "query": [None, None, None]},
             {"id": "southeast-asia", "name": "Southeast Asia", "level": "group", "parent": "", "children": ["mys"], "query": [["MYS"], None, None]},
             {"id": "mys", "name": "Malaysia", "level": "country", "parent": "southeast-asia", "children": [], "query": ["MYS", None, None], "iso": "MYS"},
             {"id": "rus", "name": "Russia", "level": "country", "parent": "", "children": [], "query": ["RUS", None, None], "iso": "RUS"},
             {"id": "arg", "name": "Argentina", "level": "country", "parent": None, "children": [], "query": ["ARG", None, None], "iso": "ARG"}]
    by_id = {a["id"]: a for a in areas}
    gj, bb = ew.geo_block(areas[0], [by_id[c] for c in areas[0]["children"]], by_id)
    assert {f["properties"]["id"] for f in gj["features"]} == {"mys", "rus"} and set(bb) == {"mys", "rus"}
