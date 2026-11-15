"""Downloadable report (PDF) for one area and date range: "download analytics and visualizations".

Built with matplotlib only (no browser or extra packages), so it works offline and in
tests. Pages:
  1. Summary: headline numbers, the selected dates compared with the same dates in every
     other year (bar chart), and the main caveats.
  2. Calendar: year x month heatmap of the harmonized record (estimates marked *).
  3. Yearly totals with their 90 % likely ranges, and what each satellite saw.
Every converted value is marked as an estimate, as everywhere in the app.
"""

from __future__ import annotations

import io
from datetime import date

import numpy as np
import pandas as pd

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
RED, LIGHT, GREY = "#b2182b", "#fdae6b", "#555555"
A4 = (8.27, 11.69)


def _text_page(fig, lines: list[tuple[str, dict]], top: float = 0.95):
    y = top
    for txt, kw in lines:
        size = kw.get("size", 10)
        fig.text(0.07, y, txt, fontsize=size, weight=kw.get("weight", "normal"), color=kw.get("color", "black"),
                 va="top", wrap=True)
        y -= kw.get("gap", 0.018 + size / 1000)
    return y


def _window_chart(ax, tot: pd.DataFrame, cmp_: dict, unit: str, d0, d1):
    labels = [str(pd.Timestamp(e).year) if pd.Timestamp(s).year == pd.Timestamp(e).year
              else f"{pd.Timestamp(s).year}/{pd.Timestamp(e).year % 100:02d}" for s, e in zip(tot["start"], tot["end"])]
    est = tot["estimated"].astype(bool).to_numpy()
    colours = np.where(tot.index == cmp_["year"], RED, np.where(est, LIGHT, "#ef8a62"))
    x = np.arange(len(tot))
    ax.bar(x, tot["total"], color=colours)
    ax.errorbar(x, tot["total"], yerr=[tot["total"] - tot["lower"], tot["upper"] - tot["total"]], fmt="none",
                ecolor="#444", elinewidth=0.7)
    ax.axhline(cmp_["median"], ls="--", color=GREY, lw=1)
    ax.text(0, cmp_["median"], f" median of other years: {cmp_['median']:,.0f}", va="bottom", fontsize=7, color=GREY)
    ax.set_xticks(x, labels, rotation=90, fontsize=7)
    ax.set_ylabel(f"{unit}, {pd.Timestamp(d0):%d %b}–{pd.Timestamp(d1):%d %b}", fontsize=8)
    ax.tick_params(axis="y", labelsize=7)
    ax.spines[["top", "right"]].set_visible(False)


def _calendar(ax, frame: pd.DataFrame, unit: str):
    s = frame["harmonized"]
    years = sorted(set(s.index.year))
    v = pd.DataFrame(np.nan, index=years, columns=range(1, 13))
    e = pd.DataFrame(False, index=years, columns=range(1, 13))
    for p, val in s.items():
        v.at[p.year, p.month] = val
        e.at[p.year, p.month] = not str(frame.at[p, "source"]).endswith("measured")
    z = np.log10(v.to_numpy(float) + 1)
    im = ax.imshow(z, aspect="auto", cmap="YlOrRd", interpolation="nearest")
    ax.set_xticks(range(12), MONTHS, fontsize=7)
    ax.set_yticks(range(len(years)), years, fontsize=6)
    big = np.nanmax(v.to_numpy(float)) if np.isfinite(v.to_numpy(float)).any() else 1
    for i, y in enumerate(years):
        for j in range(12):
            val = v.iat[i, j]
            if np.isfinite(val):
                txt = (f"{val/1000:.0f}k" if val >= 10000 else f"{val:,.0f}") + ("*" if e.iat[i, j] else "")
                dark = z[i, j] > 0.6 * np.log10(big + 1)
                ax.text(j, i, txt, ha="center", va="center", fontsize=4.6, color="white" if dark else "black")
    cb = ax.figure.colorbar(im, ax=ax, fraction=0.03, pad=0.02)
    ticks = [t for t in [1, 10, 100, 1e3, 1e4, 1e5] if t <= big * 1.01] or [1]
    cb.set_ticks(np.log10(np.array(ticks) + 1), labels=[f"{t:,.0f}" for t in ticks])
    cb.set_label(unit, fontsize=7)
    cb.ax.tick_params(labelsize=6)


def make_report(region: str, res, unit: str = "fire days", window: tuple | None = None,
                month_cmp: dict | None = None, notes: list[str] | None = None,
                generated: date | None = None, demo: bool = False) -> bytes:
    """PDF bytes. window = (d0, d1, totals, compare) from daily.window_totals/compare_window."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.backends.backend_pdf import PdfPages

    h = res.harmonization
    frame = h.frame
    annual = h.annual()
    buf = io.BytesIO()
    gen = generated or date.today()
    with PdfPages(buf) as pdf:
        # page 1: summary
        fig = plt.figure(figsize=A4)
        lines = [(f"Fire activity in {region}", {"size": 18, "weight": "bold", "gap": 0.04}),
                 (f"Harmonized burning calendar · generated {gen:%d %B %Y}", {"size": 9, "color": GREY, "gap": 0.03})]
        if demo:
            lines.append(("SYNTHETIC DEMO DATA: these numbers are not real findings.", {"size": 11, "color": RED}))
        if month_cmp:
            lines.append((f"This month so far: {month_cmp['total']:,.0f} {unit}, against a median of "
                          f"{month_cmp['median']:,.0f} for the same days in {month_cmp['first_year']}–"
                          f"{month_cmp['year'] - 1} (rank #{month_cmp['rank']} of {month_cmp['n_years']}).",
                          {"size": 10}))
        if window is not None:
            d0, d1, tot, cmp_ = window
            rng = f" (estimate, likely {cmp_['lower']:,.0f}–{cmp_['upper']:,.0f})" if cmp_["estimated"] else ""
            pct = (f"{abs(cmp_['pct_vs_median']):.0f}% {'more' if cmp_['pct_vs_median'] > 0 else 'less'} fire than the "
                   f"median of the same dates in other years ({cmp_['median']:,.0f})"
                   if np.isfinite(cmp_["pct_vs_median"]) and cmp_["median"] >= 20 else
                   "few fires on these dates in most years, so no % change is given")
            lines += [(f"Selected dates {pd.Timestamp(d0):%d %b %Y} – {pd.Timestamp(d1):%d %b %Y}: "
                       f"{cmp_['total']:,.0f} {unit}{rng}", {"size": 11, "weight": "bold"}),
                      (f"{pct}; rank #{cmp_['rank']} of {cmp_['n_years']} years (#1 = most fire).", {"size": 10})]
        y = _text_page(fig, lines)
        if window is not None and len(window[2]):
            ax = fig.add_axes([0.1, y - 0.42, 0.85, 0.36])
            _window_chart(ax, window[2], window[3], unit, window[0], window[1])
            y -= 0.5
        foot = [("What the numbers mean", {"size": 11, "weight": "bold"}),
                (f"{unit.capitalize()}: ~1 km squares where a satellite saw fire on a day, expressed as if the NOAA-20 "
                 "satellite (2018–) had watched every year.", {"size": 8}),
                ("Light bars / *: estimates converted from older satellites, with 90% likely ranges (lines).",
                 {"size": 8}),
                ("Gas flares, industry and volcanoes are removed with a mask learned from FIRMS archive labels.",
                 {"size": 8}),
                ("Satellites miss fires under thick cloud or smoke and smouldering peat. Detections count fire, not "
                 "area burned. Not an official product.", {"size": 8})]
        for n in notes or []:
            foot.append((n, {"size": 8}))
        foot.append(("Data: NASA FIRMS (MODIS C6.1, VIIRS 375 m). Method and code: burning-calendar project.",
                     {"size": 7, "color": GREY}))
        _text_page(fig, foot, top=min(y, 0.3))
        pdf.savefig(fig)
        plt.close(fig)

        # page 2: calendar
        fig = plt.figure(figsize=A4)
        fig.text(0.07, 0.96, f"Monthly calendar, {region}", fontsize=14, weight="bold", va="top")
        fig.text(0.07, 0.935, f"{unit}; darker = more fire; * = estimate from older satellites", fontsize=8,
                 color=GREY, va="top")
        ax = fig.add_axes([0.1, 0.05, 0.78, 0.86])
        _calendar(ax, frame, unit)
        pdf.savefig(fig)
        plt.close(fig)

        # page 3: yearly totals and raw satellites
        fig = plt.figure(figsize=A4)
        fig.text(0.07, 0.96, f"Yearly totals, {region}", fontsize=14, weight="bold", va="top")
        if not annual.empty:
            ax = fig.add_axes([0.1, 0.56, 0.85, 0.34])
            estd = (annual["estimated_share"] > 0).to_numpy()
            ax.bar(annual.index, annual["total"], color=np.where(estd, LIGHT, RED))
            ax.errorbar(annual.index, annual["total"], yerr=[annual["total"] - annual["lower"],
                                                              annual["upper"] - annual["total"]],
                        fmt="none", ecolor="#444", elinewidth=0.7)
            ax.set_ylabel(f"{unit} per year", fontsize=8)
            ax.tick_params(labelsize=7)
            ax.spines[["top", "right"]].set_visible(False)
            ax.set_title("Light = estimate (converted), dark = measured by NOAA-20; lines = 90% likely range",
                         fontsize=8, color=GREY)
        ax2 = fig.add_axes([0.1, 0.1, 0.85, 0.36])
        ts = res.monthly.index.to_timestamp()
        for col in res.monthly.columns:
            ax2.plot(ts, res.monthly[col], lw=0.6, label=f"{col} (raw)")
        ax2.plot(frame.index.to_timestamp(), frame["harmonized"], color=RED, lw=1.2, label="combined record")
        ax2.set_yscale("symlog", linthresh=10)
        ax2.legend(fontsize=6, ncol=3, frameon=False)
        ax2.set_title("What each satellite saw, and the combined record (monthly)", fontsize=9)
        ax2.tick_params(labelsize=7)
        ax2.spines[["top", "right"]].set_visible(False)
        pdf.savefig(fig)
        plt.close(fig)
    return buf.getvalue()
