"""Before / after figure of the harmonization for README, slides and video.

    python scripts/plot_harmonization_proof.py                 # all Asia -> docs/figures/harmonization_before_after.png
    python scripts/plot_harmonization_proof.py --area idn --out docs/figures/harmonization_idn.png

Top: each satellite's own yearly count (cell-days) and the record you get by joining them as they are
(burncal.pipeline.naive_series: NOAA-20, else S-NPP, else MODIS Terra + Aqua, month by month): a false jump in 2012.
Bottom: the harmonized record in NOAA-20 terms (web export, same numbers as the app), estimated years with
their uncertainty band. Both panels share the y scale. The 2012 step figures are the app's seam test
(2 years after vs 2 years before the switch, seasons removed), read from the web detail export.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import pandas as pd  # noqa: E402

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from burncal.pipeline import naive_series  # noqa: E402

# categorical slots 1-4 of the validated default palette (dataviz skill), fixed order
SAT = {"Terra": ("#2a78d6", "MODIS Terra"), "Aqua": ("#eb6834", "MODIS Aqua"),
       "SNPP": ("#1baf7a", "VIIRS Suomi NPP"), "NOAA20": ("#eda100", "VIIRS NOAA-20")}
INK, MUTED, GRID = "#1f1f1e", "#6b6a63", "#e6e5df"
HARM, BAND = "#2a78d6", "#86b6ef"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--area", default="_all", help="web export area file id (default _all = Asia; a country iso, e.g. idn)")
    ap.add_argument("--out", type=Path, default=ROOT / "docs" / "figures" / "harmonization_before_after.png")
    args = ap.parse_args(argv)

    data = ROOT / "web" / "public" / "data"
    area = json.loads((data / "area" / f"{args.area}.json").read_text(encoding="utf-8"))
    seams = json.loads((data / "detail" / f"{args.area}.json").read_text(encoding="utf-8"))["seams"]
    naive_step = seams["naiveStep2012"]
    harm_step = next(r["stepPct"] for r in seams["rows"] if r["seam"].startswith("2012"))
    h = pd.DataFrame(area["annual"]).set_index("years")
    first, last = int(h.index.min()), int(h.index.max())

    c = pd.read_parquet(ROOT / "data" / "processed" / "cube.parquet", columns=["month", "satellite", "country", "cell_days"])
    if area["level"] == "country":
        c = c[c["country"] == area["id"].upper()]
    monthly = c.groupby([pd.PeriodIndex(c["month"].astype(str), freq="M"), "satellite"])["cell_days"].sum().unstack()
    raw = monthly.groupby(monthly.index.year).sum(min_count=1).reindex(range(first, last + 1))
    raw.loc[2018, "NOAA20"] = float("nan")  # first NOAA-20 year is partial in the archive
    nv = naive_series(monthly)
    naive = nv.groupby(nv.index.year).sum(min_count=1).reindex(range(first, last + 1))
    big = max(naive.max(), h["upper"].max()) >= 2e6
    m, unit = (1e6, "millions") if big else (1e3, "thousands")

    fig, (a1, a2) = plt.subplots(2, 1, figsize=(11, 8.2), sharex=True, sharey=True, dpi=150)
    for ax in (a1, a2):
        ax.grid(axis="y", color=GRID, lw=0.8)
        ax.set_axisbelow(True)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        ax.spines["left"].set_color(GRID)
        ax.spines["bottom"].set_color(MUTED)
        ax.tick_params(colors=MUTED, labelsize=9)
        ax.set_ylabel(f"fire days per year ({unit})", color=MUTED, fontsize=9)

    for sat, (col, lab) in SAT.items():
        if sat in raw:
            s = raw[sat].dropna() / m
            a1.plot(s.index, s.values, color=col, lw=1.6, alpha=0.9)
            dy = {"NOAA20": 7, "SNPP": -7}.get(sat, 0)  # the two VIIRS lines end close together
            a1.annotate(lab, (s.index[-1], s.values[-1]), xytext=(6, dy), textcoords="offset points",
                        color=INK, fontsize=8.5, va="center")
    a1.plot(naive.index, naive / m, color=INK, lw=2.4, ls=(0, (4, 2)))
    j0, j1 = naive.loc[2011], naive.loc[2012]
    top = max(naive.max(), h["upper"].max()) / m
    a1.annotate(f"false jump: {naive_step:+.0f} %\nwhen the record switches\nfrom MODIS to VIIRS (2012)",
                xy=(2011.95, (j0 + j1) / 2 / m), xytext=(2004.6, top * 0.5), color=INK, fontsize=9,
                arrowprops=dict(arrowstyle="->", color=INK, lw=1))
    a1.set_title("Before: each satellite counts differently; joined as they are (dashed), the record jumps",
                 loc="left", color=INK, fontsize=11, weight="bold")

    est = h[h["estimatedShare"] > 0.5]
    meas = h[h["estimatedShare"] <= 0.5]
    a2.fill_between(est.index, est["lower"] / m, est["upper"] / m, color=BAND, alpha=0.45, lw=0)
    a2.plot(est.index, est["total"] / m, color=HARM, lw=2.4, ls=(0, (4, 2)))
    a2.plot(meas.index, meas["total"] / m, color=HARM, lw=2.4)
    a2.plot([est.index[-1], meas.index[0]], [est["total"].iloc[-1] / m, meas["total"].iloc[0] / m], color=HARM, lw=2.4, ls=(0, (4, 2)))
    h0, h1 = h.loc[2011, "total"], h.loc[2012, "total"]
    a2.annotate(f"step at 2012: {harm_step:+.0f} %,\nan ordinary year-to-year change", xy=(2011.9, (h0 + h1) / 2 / m),
                xytext=(2008.3, top * 0.26), color=INK, fontsize=9, arrowprops=dict(arrowstyle="->", color=INK, lw=1))
    a2.set_title("After: one harmonized record in NOAA-20 terms, no jump at satellite changes",
                 loc="left", color=INK, fontsize=11, weight="bold")
    a2.text(est.index[0], top * 0.04, "estimated from MODIS / S-NPP\n(dashed, with 90 % band)", color=MUTED, fontsize=8.5)
    a2.text(meas.index[0] + 0.3, meas["total"].max() / m * 1.07, "measured by NOAA-20", color=MUTED, fontsize=8.5)
    a2.set_ylim(0, top * 1.08)
    a2.set_xlim(first - 0.5, last + 2.2)
    fig.text(0.01, 0.005, f"{area['name']}, {first}–{last}. Fire days = ~1 km squares with a detection on a day (NASA FIRMS, "
             "cleaned).\nStep = 2 years after vs 2 years before the switch, seasons removed. Same numbers as the app.",
             color=MUTED, fontsize=8)
    fig.tight_layout(rect=(0, 0.035, 1, 1))
    args.out.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(args.out, facecolor="white")
    print(f"2012 step: naive {naive_step:+.0f} %, harmonized {harm_step:+.0f} % -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
