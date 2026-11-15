"""PDF report (synthetic demo data)."""

import pandas as pd

from burncal.io import make_demo_data
from burncal.pipeline import run
from burncal.report import make_report


def test_report_is_a_pdf_with_three_pages():
    res = run(make_demo_data())
    pdf = make_report("Demo", res, demo=True, notes=["test note"])
    assert pdf[:5] == b"%PDF-" and pdf.count(b"/Type /Page") - pdf.count(b"/Type /Pages") == 3


def test_report_with_window():
    res = run(make_demo_data())
    f = res.harmonization.frame
    years = sorted(set(f.index.year))[1:-1]
    tot = pd.DataFrame({"start": [pd.Timestamp(f"{y}-03-01") for y in years],
                        "end": [pd.Timestamp(f"{y}-03-31") for y in years],
                        "total": [float(f["harmonized"].get(pd.Period(f"{y}-03", "M"), 0)) for y in years]},
                       index=years)
    tot["lower"], tot["upper"], tot["estimated"] = tot["total"] * 0.8, tot["total"] * 1.2, False
    cmp_ = {"year": years[-1], "total": tot["total"].iloc[-1], "median": tot["total"].median(), "pct_vs_median": 10.0,
            "rank": 2, "n_years": len(years), "estimated": False, "lower": 0, "upper": 0, "first_year": years[0]}
    pdf = make_report("Demo", res, window=(tot["start"].iloc[-1], tot["end"].iloc[-1], tot, cmp_))
    assert len(pdf) > 10_000


def test_report_marks_only_converted_months():
    import numpy as np
    from burncal.report import _calendar
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    idx = pd.period_range("2017-11", "2018-02", freq="M")
    frame = pd.DataFrame({"harmonized": [10.0, 20, 30, 40],
                          "source": ["SNPP converted (M1)", "SNPP converted (M1)", "NOAA20 measured", "NOAA20 measured"]},
                         index=idx)
    fig, ax = plt.subplots()
    _calendar(ax, frame, "fire days")
    texts = sorted(t.get_text() for t in ax.texts)
    plt.close(fig)
    assert texts == ["10*", "20*", "30", "40"]
