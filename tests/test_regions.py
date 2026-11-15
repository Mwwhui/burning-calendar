

def test_argentina_is_studied_but_never_in_asian_totals():
    from burncal.regions import ASIA_ISO3, OTHER_ISO3, STUDY_ISO3, as_isos
    assert "ARG" in OTHER_ISO3 and "ARG" in STUDY_ISO3
    assert "ARG" not in ASIA_ISO3 and "ARG" not in as_isos(None)


def test_name_fixes_applied(tmp_path):
    import json
    from burncal.regions import load_layer
    p = tmp_path / "b.geojson"
    sq = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}
    p.write_text(json.dumps({"type": "FeatureCollection", "features": [
        {"type": "Feature", "properties": {"shapeName": "Río negro"}, "geometry": sq}]}), encoding="utf-8")
    names, _ = load_layer(p)
    assert list(names) == ["Río Negro"]
