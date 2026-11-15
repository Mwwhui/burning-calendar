import json

import numpy as np
import pandas as pd
import pytest

pytest.importorskip("shapely")

from burncal.context import el_nino_years, enso_by_year, enso_phase, load_oni  # noqa: E402
from burncal.regions import DEFAULT_DIR, assign_regions, filter_region  # noqa: E402


def square(x0, y0, x1, y1):
    return {"type": "Polygon", "coordinates": [[[x0, y0], [x1, y0], [x1, y1], [x0, y1], [x0, y0]]]}


def write_layer(path, features):
    gj = {"type": "FeatureCollection",
          "features": [{"type": "Feature", "properties": {"shapeName": n}, "geometry": g} for n, g in features]}
    path.write_text(json.dumps(gj))


@pytest.fixture
def fake_boundaries(tmp_path):
    # Malaysia = x 0..2, split into two states and one district; Indonesia = x 3..4
    write_layer(tmp_path / "geoBoundaries-MYS-ADM0.geojson", [("Malaysia", square(0, 0, 2, 1))])
    write_layer(tmp_path / "geoBoundaries-MYS-ADM1.geojson", [("StateA", square(0, 0, 1, 1)), ("StateB", square(1, 0, 2, 1))])
    write_layer(tmp_path / "geoBoundaries-MYS-ADM2.geojson", [("DistA1", square(0, 0, 1, 1))])
    write_layer(tmp_path / "geoBoundaries-IDN-ADM1.geojson", [("Riau", square(3, 0, 4, 1))])
    return tmp_path


def test_assign_regions(fake_boundaries):
    df = pd.DataFrame({
        "longitude": [0.5, 1.5, 3.5, 2.03, 2.5, 0.5],
        "latitude":  [0.5, 0.5, 0.5, 0.5, 0.5, 0.5],   # last row repeats the first coordinate
        "id": range(6),
    })
    out = assign_regions(df, fake_boundaries, snap_deg=0.05).sort_values("id")
    assert out["country"].tolist() == ["MYS", "MYS", "IDN", "MYS", "Other", "MYS"]  # 2.03 snapped, 2.5 is sea
    assert out["adm1"].tolist()[:3] == ["StateA", "StateB", "Riau"]
    assert out["adm2"].iloc[0] == "DistA1" and pd.isna(out["adm2"].iloc[1])
    assert len(out) == len(df)
    assert len(filter_region(out, "MYS", adm1="StateB")) == 2  # incl. the snapped coastal point
    assert len(filter_region(out, "IDN", adm1=["Riau"])) == 1


def test_missing_boundaries_message(tmp_path):
    with pytest.raises(FileNotFoundError, match="download_context"):
        assign_regions(pd.DataFrame({"longitude": [1.0], "latitude": [1.0]}), tmp_path)


@pytest.mark.skipif(not (DEFAULT_DIR / "geoBoundaries-MYS-ADM1.geojson").exists(), reason="real boundaries not downloaded")
def test_real_boundaries_known_places():
    df = pd.DataFrame({
        "longitude": [101.69, 110.35, 116.07, 101.45, 114.94, 117.2],
        "latitude":  [3.14,   1.55,   5.98,   0.53,   4.89,   1.97],
    })  # Kuala Lumpur, Kuching, Kota Kinabalu, Pekanbaru (Riau), Bandar Seri Begawan, East Kalimantan
    out = assign_regions(df)
    assert out["country"].tolist() == ["MYS", "MYS", "MYS", "IDN", "BRN", "IDN"]
    assert out["adm1"].tolist()[:4] == ["Kuala Lumpur", "Sarawak", "Sabah", "Riau"]


ONI_TXT = """ SEAS  YR   TOTAL   ANOM
""" + "".join(
    f"  {s} {y}  27.00  {a:.2f}\n"
    for y, vals in [(2014, [0.0] * 6 + [0.6] * 6), (2015, [0.6] * 12), (2016, [0.6] * 3 + [-0.6] * 9)]
    for s, a in zip(["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"], vals)
)


def test_oni_and_enso(tmp_path):
    p = tmp_path / "oni.txt"
    p.write_text(ONI_TXT)
    oni = load_oni(p)
    assert oni.index[0] == pd.Period("2014-01", "M") and oni.index[-1] == pd.Period("2016-12", "M")
    phase = enso_phase(oni)
    assert phase[pd.Period("2015-06", "M")] == "El Nino"
    assert phase[pd.Period("2016-12", "M")] == "La Nina"
    assert phase[pd.Period("2014-01", "M")] == "Neutral"
    assert el_nino_years(oni) == [2014, 2015]
    t = enso_by_year(oni)
    assert t.loc[2016, "label"] == "La Nina" and t["complete"].all()


def test_short_run_is_not_an_episode(tmp_path):
    vals = [0.0, 0.6, 0.6, 0.6, 0.6, 0.0] + [0.0] * 6
    seasons = ["DJF", "JFM", "FMA", "MAM", "AMJ", "MJJ", "JJA", "JAS", "ASO", "SON", "OND", "NDJ"]
    p = tmp_path / "oni.txt"
    p.write_text(" SEAS YR TOTAL ANOM\n" + "".join(f"{s} 2000 27 {a}\n" for s, a in zip(seasons, vals)))
    assert (enso_phase(load_oni(p)) == "Neutral").all()  # 4 seasons only


@pytest.mark.skipif(not (DEFAULT_DIR / "oni.ascii.txt").exists(), reason="ONI not downloaded")
def test_real_oni_known_el_nino_years():
    years = el_nino_years(load_oni())
    for y in (1997, 2015, 2023):
        assert y in years
    assert 2011 not in years  # La Nina year
