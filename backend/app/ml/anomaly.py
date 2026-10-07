"""Unusual-event detection maths (pure functions, no I/O).

The model's one-day-ahead quantiles define, for every observed day, a probability-integral-transform value (PIT) and its
normal score z. If the model is calibrated, z is ~N(0, 1); on this data the centre is (sd 0.99) but the upper tail is heavy
(z > 2.33 on 2.5% of days instead of 1%), so a SINGLE extreme day is ordinary and never enough on its own. Two detectors:
  jump  : two consecutive days both beyond z = 1.64 (about the 95th percentile) and at least 25% off the median forecast
  shift : a sustained drift, found with a one-sided CUSUM on z (reference k = 0.75, decision interval h = 5, >= 3 days)
Measured on shock-free data these fire on about 0.3% of agent-flow-nights each (see the evaluation in the README).
Days on which the agent ran out of stock are CENSORED: the observed value is only a lower bound on demand, so they may
confirm an upward departure but never a downward one.
"""
from __future__ import annotations

import numpy as np
from scipy.special import ndtri

from . import liquidity_forecaster as lf

LEVELS = np.array(lf.QUANTILES)
Z_JUMP = 1.64
MIN_MOVE = 0.25            # a jump must also be at least 25% away from the median forecast
CUSUM_K, CUSUM_H = 0.75, 5.0
MIN_RUN = 3                # a shift needs at least three days of evidence
WINDOW = 14
SHRINK = 0.7               # the model's lag features partly adapt by themselves, so only 70% of the gap is proposed as a multiplier
MULT_BOUNDS = (0.5, 2.5)


def pit(y: float, q) -> float:
    """CDF of y through the piecewise-linear quantile function (tails extrapolated), clipped away from 0 and 1."""
    lo = max(0.0, q[0] - 0.75 * (q[2] - q[0]))
    hi = q[-1] + 0.75 * (q[-1] - q[2])
    xs = np.concatenate([[lo], q, [hi]])
    xs = np.maximum.accumulate(xs + 1e-9 * np.arange(len(xs)))
    return float(np.clip(np.interp(y, xs, np.concatenate([[0.0], LEVELS, [1.0]])), 1e-3, 1 - 1e-3))


def zscore(y: float, q) -> float:
    return float(ndtri(pit(y, q)))


def cusum(z, k: float = CUSUM_K, h: float = CUSUM_H) -> dict:
    """One-sided CUSUMs over a z series (oldest first). Returns the final statistics and how many trailing days
    the current run has lasted (days since the statistic was last zero)."""
    up = dn = 0.0
    run_up = run_dn = 0
    for v in z:
        up, dn = max(0.0, up + v - k), max(0.0, dn - v - k)
        run_up = run_up + 1 if up > 0 else 0
        run_dn = run_dn + 1 if dn > 0 else 0
    return dict(up=up, down=dn, run_up=run_up, run_down=run_dn, alarm_up=up > h, alarm_down=dn > h)


def detect_flow(y, q, censored, window: int = WINDOW) -> dict | None:
    """y: observed values (oldest first, last = today), q: matching (n, 5) quantile rows, censored: bool per day.
    Returns the strongest detection that ends today, or None."""
    y = np.asarray(y, float)
    n = len(y)
    if n < MIN_RUN + 3:
        return None
    z = ndtri(np.array([pit(y[i], q[i]) for i in range(n)]))
    cen = np.asarray(censored, bool)
    z_up = np.where(cen, np.maximum(z, 0.0), z)          # a censored day can only confirm "higher than forecast"
    z_dn = np.where(cen, 0.0, z)
    ratio = y / np.maximum(np.array([q[i][2] for i in range(n)]), 1.0)
    out = None
    for direction, zz, sign in (("up", z_up, 1), ("down", z_dn, -1)):
        c = cusum(zz[-window:])
        run = c["run_up" if direction == "up" else "run_down"]
        shift = c["alarm_up" if direction == "up" else "alarm_down"] and run >= MIN_RUN
        jump = bool(np.all(zz[-2:] * sign >= Z_JUMP) and np.all((ratio[-2:] - 1.0) * sign >= MIN_MOVE))
        if not (jump or shift):
            continue
        k = max(1, min(run, window)) if shift else 2
        raw = float(np.median(ratio[-k:]))
        mult = float(np.clip(1.0 + SHRINK * (raw - 1.0), *MULT_BOUNDS))
        stat = c["up" if direction == "up" else "down"]
        cand = dict(kind="shift" if shift else "jump", direction=direction, days=int(k), z_last=round(float(zz[-1]), 2),
                    cusum=round(float(stat), 2), raw_ratio=round(raw, 3), multiplier=round(mult, 2))
        if out is None or cand["cusum"] > out["cusum"]:
            out = cand
    return out
