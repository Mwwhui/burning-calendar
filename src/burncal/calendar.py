"""Burning calendar: year x month grids, anomalies, season-to-date and plotting."""

from __future__ import annotations

import numpy as np
import pandas as pd

MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


def to_grid(series: pd.Series) -> pd.DataFrame:
    """PeriodIndex monthly series -> DataFrame (rows = years, columns = 1..12)."""
    df = pd.DataFrame({"v": series.to_numpy(), "year": series.index.year, "mon": series.index.month})
    grid = df.pivot(index="year", columns="mon", values="v").reindex(columns=range(1, 13))
    grid.columns.name = None
    return grid


def _baseline(grid: pd.DataFrame, baseline_years) -> pd.DataFrame:
    a, b = baseline_years
    return grid.loc[a:b]


def anomaly_z(grid: pd.DataFrame, baseline_years) -> pd.DataFrame:
    """z-score of log1p counts against the same calendar month in the baseline years.

    Log scale keeps one extreme year from dominating, and quiet months with tiny
    baselines don't explode the way percentages do.
    """
    lg = np.log1p(grid)
    base = _baseline(lg, baseline_years)
    sd = base.std().replace(0, np.nan)
    return (lg - base.mean()) / sd


def anomaly_pct(grid: pd.DataFrame, baseline_years, min_baseline: float = 1.0) -> pd.DataFrame:
    """Percent difference from the baseline monthly mean; NaN where the mean < min_baseline."""
    mean = _baseline(grid, baseline_years).mean()
    mean = mean.where(mean >= min_baseline)
    return 100 * (grid - mean) / mean


def season_to_date(series: pd.Series, year: int, through_month: int | None = None) -> pd.DataFrame:
    """Cumulative Jan..through_month totals for every year, ranked (1 = most fire).

    Answers the brief's question "is this year more active than usual up to now?".
    `through_month` defaults to the last month with data in `year`.
    """
    grid = to_grid(series)
    if through_month is None:
        row = grid.loc[year] if year in grid.index else pd.Series(dtype=float)
        valid = row.dropna()
        if valid.empty:
            raise ValueError(f"No data for {year}")
        through_month = int(valid.index.max())
    part = grid.loc[:, 1:through_month]
    complete = part.notna().all(axis=1)
    total = part.sum(axis=1).where(complete)
    out = pd.DataFrame({"to_date": total})
    out["rank"] = out["to_date"].rank(ascending=False, method="min")
    hist = out.drop(index=year, errors="ignore")["to_date"].dropna()
    out.attrs.update({
        "year": year, "through_month": through_month,
        "hist_median": float(hist.median()) if len(hist) else np.nan,
        "pct_vs_median": (float(100 * (out.loc[year, "to_date"] / hist.median() - 1))
                          if len(hist) and year in out.index and hist.median() > 0 else np.nan),
    })
    return out


def plot_calendar(values: pd.DataFrame, title: str, cmap: str = "YlOrRd", fmt=lambda v: f"{v:,.0f}",
                  vmin=None, vmax=None, label: str = "", estimated: pd.DataFrame | None = None, ax=None,
                  year_marks: dict | None = None):
    """Heatmap with numbers in each cell. `estimated` (bool grid) gets a dashed outline.

    year_marks: {year: "EN"} appends a label to that row, e.g. El Nino years from
    burncal.context.el_nino_years.
    """
    import matplotlib.pyplot as plt

    if ax is None:
        _, ax = plt.subplots(figsize=(11, 0.32 * len(values) + 1.5))
    im = ax.imshow(values.to_numpy(float), aspect="auto", cmap=cmap, vmin=vmin, vmax=vmax)
    ax.set_xticks(range(12), MONTHS)
    marks = year_marks or {}
    ax.set_yticks(range(len(values)), [f"{y} {marks[y]}" if y in marks else str(y) for y in values.index])
    diverging = vmin is not None and vmax is not None and vmin < 0 < vmax
    for i, y in enumerate(values.index):
        for j, m in enumerate(values.columns):
            v = values.loc[y, m]
            if pd.isna(v):
                continue
            nv = im.norm(v)
            dark = abs(nv - 0.5) > 0.32 if diverging else nv > 0.6
            ax.text(j, i, fmt(v), ha="center", va="center", fontsize=7, color="white" if dark else "black")
            if estimated is not None and bool(estimated.loc[y, m]):
                ax.add_patch(plt.Rectangle((j - .5, i - .5), 1, 1, fill=False, ec="grey", lw=.4, ls="--"))
    plt.colorbar(im, ax=ax, label=label, fraction=.025)
    ax.set_title(title)
    return ax
