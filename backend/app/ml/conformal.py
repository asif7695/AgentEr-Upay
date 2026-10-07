"""Conformalized quantile regression (CQR) for the P10-P90 and P25-P75 intervals.

Calibrated on a window that was never used for fitting. Score E = max(q_lo - y, y - q_hi) in RELATIVE units
(demand / the agent's 28-day mean), per flow and agent type; the interval is widened (or tightened) by the
finite-sample-corrected quantile of E so that it covers its nominal share on exchangeable data.
Applied on top of any quantile model, before the risk simulation."""
from __future__ import annotations

import math

import numpy as np

PAIRS = {"p10_p90": (0, 4, 0.80), "p25_p75": (1, 3, 0.50)}


def _delta(r, qlo, qhi, cover):
    e = np.maximum(qlo - r, r - qhi)
    n = len(e)
    if n < 30:
        return None
    level = min(1.0, math.ceil((n + 1) * cover) / n)
    return float(np.quantile(e, level))


def fit(Q_rel: dict, y_rel: dict, keep: dict, types) -> dict:
    """Q_rel[flow]: (N,5) relative quantiles; y_rel[flow]: (N,) relative observed; keep[flow]: uncensored mask;
    types: (N,) location_type. Returns {flow: {pair: {"_all": d, type: d, ...}}}."""
    out = {}
    types = np.asarray(types)
    for flow in ("co", "ci"):
        out[flow] = {}
        for name, (lo, hi, c) in PAIRS.items():
            k = np.asarray(keep[flow])
            d_all = _delta(y_rel[flow][k], Q_rel[flow][k, lo], Q_rel[flow][k, hi], c)
            entry = {"_all": d_all if d_all is not None else 0.0}
            for t in np.unique(types):
                m = k & (types == t)
                d = _delta(y_rel[flow][m], Q_rel[flow][m, lo], Q_rel[flow][m, hi], c)
                entry[str(t)] = d if d is not None else entry["_all"]
            out[flow][name] = entry
    return out


def apply(Q: np.ndarray, scale: np.ndarray, calib_flow: dict, types) -> np.ndarray:
    """Q: (N,5) quantiles in BDT, scale: (N,) -> calibrated (N,5), still sorted and >= 0."""
    types = np.asarray(types)
    rel = Q / scale[:, None]
    out = rel.copy()
    for name, (lo, hi, _) in PAIRS.items():
        d = np.array([calib_flow[name].get(str(t), calib_flow[name]["_all"]) for t in types])
        out[:, lo] = rel[:, lo] - d
        out[:, hi] = rel[:, hi] + d
    out = np.sort(np.maximum(out, 0.0), axis=1)
    return out * scale[:, None]
