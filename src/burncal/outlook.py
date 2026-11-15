"""Seasonal outlook: will the next fire season be below normal, normal or above normal?

A simple, testable statistical outlook (like the tercile outlooks of weather services):

1. The fire season of an area = its 3 consecutive calendar months with the most fire on
   average (harmonized series), e.g. Aug-Oct for Indonesia, Feb-Apr for Thailand.
2. Predictor = the Oceanic Nino Index (ONI, NOAA CPC) of the newest month already
   published. El Nino dries most of Southeast Asia and is the best-known driver of big fire
   years (1997, 2015, 2019 with a positive IOD, 2023). The lead (months from that ONI month
   to the season start) is the same in the fit as in the outlook.
3. log(season total) = a + b * ONI, fitted on past seasons. Chances of the three terciles
   (the driest, middle and wettest third of past seasons) come from a normal spread equal
   to the leave-one-year-out error.
4. Skill is checked by leave-one-year-out hindcasts for every lead from 1 to 12 months,
   so the app can say from which month an outlook becomes useful. The outlook is shown only when it
   beat "every year is average" (MSSS >= MIN_MSSS) and the correlation is at least MIN_R;
   otherwise the app says that climate indices give no useful outlook for this area.

The Indian Ocean Dipole (DMI) was tested too (docs/decisions.md): it added skill in one
of 12 areas and the published index runs about 4 months behind, so it is not used.
"""

from __future__ import annotations

from math import erf, sqrt

import numpy as np
import pandas as pd

MIN_R = 0.4
MIN_MSSS = 0.1
MIN_SEASONS = 12
P_CAP = (0.05, 0.90)  # shown chances are kept inside this range (an outlook is never certain)


def peak_season(h: pd.Series) -> tuple[list[int], float]:
    """The 3 consecutive months (may wrap over New Year) with the most fire, and their share."""
    clim = h.groupby(h.index.month).mean().reindex(range(1, 13)).fillna(0.0)
    tot = {m: sum(clim[(m + k - 1) % 12 + 1] for k in range(3)) for m in range(1, 13)}
    m0 = max(tot, key=tot.get)
    return [(m0 + k - 1) % 12 + 1 for k in range(3)], float(tot[m0] / max(clim.sum(), 1e-9))


def _season_periods(year: int, months: list[int]) -> list[pd.Period]:
    """Months of the season that starts in `year` (later months may fall in year + 1)."""
    m0 = months[0]
    return [pd.Period(year=year + (1 if m < m0 else 0), month=m, freq="M") for m in months]


def season_table(h: pd.Series, oni: pd.Series, months: list[int], lead: int) -> pd.DataFrame:
    """Per season start year: season total (only complete seasons) and ONI `lead` months before the start."""
    rows = []
    for y in range(h.index.min().year, h.index.max().year + 1):
        per = _season_periods(y, months)
        vals = [h.get(p, np.nan) for p in per]
        if not np.all(np.isfinite(vals)):
            continue
        pm = per[0] - lead
        rows.append({"year": y, "total": float(np.sum(vals)), "oni": oni.get(pm, np.nan)})
    t = pd.DataFrame(rows, columns=["year", "total", "oni"]).dropna().set_index("year")
    t["log"] = np.log1p(t["total"])
    return t


def hindcast(t: pd.DataFrame) -> dict:
    """Leave-one-year-out test of log(total) ~ ONI against the climatological mean."""
    n = len(t)
    if n < MIN_SEASONS:
        return {"n": n, "useful": False}
    X = np.c_[np.ones(n), t["oni"].to_numpy()]
    y = t["log"].to_numpy()
    pred, clim = np.empty(n), np.empty(n)
    for i in range(n):
        k = np.arange(n) != i
        b = np.linalg.lstsq(X[k], y[k], rcond=None)[0]
        pred[i], clim[i] = X[i] @ b, y[k].mean()
    r = float(np.corrcoef(pred, y)[0, 1]) if np.std(pred) > 0 else 0.0
    msss = float(1 - np.mean((pred - y) ** 2) / np.mean((clim - y) ** 2))
    hits = 0
    for i in range(n):
        q = np.quantile(np.delete(y, i), [1 / 3, 2 / 3])
        hits += int(np.digitize(pred[i], q) == np.digitize(y[i], q))
    return {"n": n, "r": r, "msss": msss, "hits": hits, "rmse": float(np.sqrt(np.mean((pred - y) ** 2))),
            "useful": bool(r >= MIN_R and msss >= MIN_MSSS), "pred": pd.Series(pred, t.index)}


def _ncdf(x: float) -> float:
    return 0.5 * (1 + erf(x / sqrt(2)))


def outlook(h: pd.Series, oni: pd.Series, today: pd.Timestamp | None = None) -> dict:
    """Outlook for the next season that has not started yet, with its hindcast skill.

    h: harmonized monthly series (PeriodIndex). oni: monthly ONI (PeriodIndex, newest last).
    """
    h = h.dropna()
    months, share = peak_season(h)
    today = pd.Timestamp(today) if today is not None else pd.Timestamp.today()
    now = pd.Period(today, "M")
    start = pd.Period(year=now.year, month=months[0], freq="M")
    if start <= now:
        start = pd.Period(year=now.year + 1, month=months[0], freq="M")
    last_oni = oni.dropna().index.max()
    lead = int((start - last_oni).n)
    t = season_table(h, oni, months, lead)
    sk = hindcast(t)
    out = {"months": months, "share": share, "season_start": start, "oni_month": last_oni,
           "oni": float(oni[last_oni]), "lead": lead, "skill": sk, "seasons": t,
           "useful_leads": [L for L in range(1, 13) if hindcast(season_table(h, oni, months, L)).get("useful")],
           "past_extremes": int((t["oni"].abs() >= abs(float(oni[last_oni])) - 0.3).sum())}
    if not sk.get("useful"):
        return out
    X = np.c_[np.ones(len(t)), t["oni"].to_numpy()]
    b = np.linalg.lstsq(X, t["log"].to_numpy(), rcond=None)[0]
    mu = float(b[0] + b[1] * out["oni"])
    q1, q2 = np.quantile(t["log"], [1 / 3, 2 / 3])
    sd = sk["rmse"]
    p_low = float(np.clip(_ncdf((q1 - mu) / sd), *P_CAP))
    p_high = float(np.clip(1 - _ncdf((q2 - mu) / sd), *P_CAP))
    if p_low + p_high > 1 - P_CAP[0]:
        p_low, p_high = (p_low, 1 - P_CAP[0] - p_low) if p_low > p_high else (1 - P_CAP[0] - p_high, p_high)
    out.update({
        "expected": float(np.expm1(mu)), "normal_low": float(np.expm1(q1)), "normal_high": float(np.expm1(q2)),
        "p_below": p_low, "p_normal": 1 - p_low - p_high, "p_above": p_high, "slope": float(b[1]),
    })
    return out
