"""Multi-day path dependence: estimate it from OUT-OF-FIT residuals of our calibrated challenger, then test the
simulated 3- and 7-day cumulative tails on the untouched Sep-Dec period.

Models compared (all feed the SUPPLIED lf.sample_flows through app.ml.dependence.CopulaRNG):
  independent : supplied default (days and flows drawn independently)
  correlated  : Gaussian copula, full 14x14 matrix per agent type
  ar1         : parametric auto-regressive path, corr(i, j) = rho_day^|i-j| within a flow, rho_cross across flows
  t_copula    : the full matrix with a Student-t copula (nu = 4, 6, 10): extreme days cluster
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import norm

from app.ml import liquidity_forecaster as lf
from app.ml.dependence import CopulaRNG, ar1_corr, nearest_psd_corr
from .data import uncensored

H = lf.H
LEVELS = np.array(lf.QUANTILES)


def pit(y, q):
    lo = max(0.0, q[0] - 0.75 * (q[2] - q[0]))
    hi = q[-1] + 0.75 * (q[-1] - q[2])
    xs = np.concatenate([[lo], q, [hi]])
    xs = np.maximum.accumulate(xs + 1e-9 * np.arange(len(xs)))
    return float(np.clip(np.interp(y, xs, np.concatenate([[0.0], LEVELS, [1.0]])), 1e-3, 1 - 1e-3))


def residual_matrix(F: pd.DataFrame, Q: dict, window_mask: pd.Series) -> pd.DataFrame:
    """One row per (agent, origin): z-scores of the 7 cash-out then 7 cash-in outcomes (NaN where censored)."""
    d = F[window_mask].copy()
    idx = d.index.to_numpy()
    d["z_co"] = [norm.ppf(pit(y, q)) for y, q in zip(d["y_co"].to_numpy(), Q["co"][idx])]
    d["z_ci"] = [norm.ppf(pit(y, q)) for y, q in zip(d["y_ci"].to_numpy(), Q["ci"][idx])]
    d.loc[~uncensored(d, "co"), "z_co"] = np.nan
    d.loc[~uncensored(d, "ci"), "z_ci"] = np.nan
    full = d.groupby(["agent_id", "origin_date"])["h"].transform("count") == H          # all 7 targets inside the window
    w = d[full].pivot_table(index=["agent_id", "origin_date"], columns="h", values=["z_co", "z_ci"], dropna=False)
    w.columns = [f"{a}_{b}" for a, b in w.columns]
    return w[[f"z_co_{h}" for h in range(1, H + 1)] + [f"z_ci_{h}" for h in range(1, H + 1)]]


def estimate(wide: pd.DataFrame, types: pd.Series) -> dict:
    def corr_of(w):
        return nearest_psd_corr(w.corr(min_periods=30).fillna(0.0).to_numpy())
    pooled = corr_of(wide)
    t_of = wide.index.get_level_values("agent_id").map(types)
    by_type = {t: corr_of(wide[t_of == t]) for t in sorted(types.unique())}
    rho_day = float(np.mean([pooled[i, i + 1] for i in range(H - 1)] + [pooled[H + i, H + i + 1] for i in range(H - 1)]))
    rho_cross = float(np.mean([pooled[i, H + i] for i in range(H)]))
    return dict(pooled=pooled, by_type=by_type, rho_day=rho_day, rho_cross=rho_cross, n_origins=int(len(wide)))


def evaluate_tails(F: pd.DataFrame, Q: dict, test_mask: pd.Series, est: dict, types: pd.Series, n_paths=4000, stride=2) -> dict:
    """Rates at which the observed cumulative 3-/7-day demand leaves the simulated interval, per dependence model."""
    d = F[test_mask].assign(_i=F[test_mask].index)       # keep the original row index: Q is aligned to F
    keys = d[["agent_id", "origin_date"]].drop_duplicates().sort_values(["origin_date", "agent_id"]).iloc[::stride]
    groups = {tuple(k): g.sort_values("h") for k, g in d.merge(keys, on=["agent_id", "origin_date"]).groupby(["agent_id", "origin_date"])}
    ar = ar1_corr(est["rho_day"], est["rho_cross"])
    models = {"independent": None, "correlated": (None, None), "ar1": (ar, None),
              "t_copula_nu4": (None, 4), "t_copula_nu6": (None, 6), "t_copula_nu10": (None, 10)}
    acc = {m: {k: {"co_up95": [], "co_up99": [], "net_up95": [], "net_up99": [], "net_lo05": [], "net_lo01": [], "co_in80": [], "co_in95": []}
               for k in (3, 7)} for m in models}
    for i, ((aid, od), g) in enumerate(groups.items()):
        if len(g) < H:
            continue
        ok_co = bool(uncensored(g, "co").all())
        ok_both = ok_co and bool(uncensored(g, "ci").all())
        if not ok_co:
            continue
        gi = g["_i"].to_numpy()
        qco, qci = Q["co"][gi], Q["ci"][gi]
        typ = types[aid]
        corr_full = nearest_psd_corr(np.array(est["by_type"][typ]))
        for m, spec in models.items():
            if spec is None:
                rng = np.random.default_rng(i)
            else:
                cm, nu = spec
                rng = CopulaRNG(i, corr_full if cm is None else cm, n_paths, nu)
            co, ci = lf.sample_flows(qco, qci, LEVELS, n_paths, rng)
            for k in (3, 7):
                cum_co = np.cumsum(co, axis=1)[:, k - 1]
                a = float(g["y_co"].iloc[:k].sum())
                r = acc[m][k]
                r["co_up95"].append(a > np.quantile(cum_co, 0.95))
                r["co_up99"].append(a > np.quantile(cum_co, 0.99))
                lo, hi = np.quantile(cum_co, [0.10, 0.90])
                r["co_in80"].append(lo <= a <= hi)
                lo, hi = np.quantile(cum_co, [0.025, 0.975])
                r["co_in95"].append(lo <= a <= hi)
                if ok_both:
                    net = np.cumsum(co - ci, axis=1)[:, k - 1]
                    an = float((g["y_co"].iloc[:k] - g["y_ci"].iloc[:k]).sum())
                    r["net_up95"].append(an > np.quantile(net, 0.95))
                    r["net_up99"].append(an > np.quantile(net, 0.99))
                    r["net_lo05"].append(an < np.quantile(net, 0.05))
                    r["net_lo01"].append(an < np.quantile(net, 0.01))
    out = {}
    nominal = {"co_up95": 0.05, "co_up99": 0.01, "net_up95": 0.05, "net_up99": 0.01, "net_lo05": 0.05, "net_lo01": 0.01, "co_in80": 0.80, "co_in95": 0.95}
    for m in models:
        out[m] = {}
        for k in (3, 7):
            rates = {kk: (float(np.mean(v)) if v else None) for kk, v in acc[m][k].items()}
            tail = [abs(rates[t] - nominal[t]) for t in ("co_up95", "co_up99", "net_up95", "net_up99", "net_lo05", "net_lo01") if rates[t] is not None]
            out[m][f"{k}d"] = dict(rates=rates, n_windows=len(acc[m][k]["co_up95"]), tail_error=float(np.mean(tail)),
                                   coverage_error=float(np.mean([abs(rates["co_in80"] - 0.80), abs(rates["co_in95"] - 0.95)])))
    out["_nominal"] = nominal
    return out
