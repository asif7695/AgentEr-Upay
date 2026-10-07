"""Adaptive decision rules: an agent's behaviour profile -> small, bounded, explainable changes to that agent's coverage,
safety buffer and alert thresholds. Pure functions (no I/O), deterministic, unit-tested.

Design principles
  * Evidence gates: nothing moves until there is enough history, and a coverage change needs STATISTICALLY significant
    miscalibration (z-score), so noise never moves a setting.
  * Shrinkage: alert precision is pooled with the network average (Beta prior), so a few alerts cannot swing a threshold.
  * Hard bounds on every setting and on how far one change may move it; a cool-down between changes.
  * Every change carries a machine-readable reason (code + numbers) that the UI renders in the user's language.
"""
from __future__ import annotations

import math
from statistics import median

GUARD = dict(
    min_days=20,                 # uncensored days needed before any model-calibration based change
    z_gate=1.5,                  # |z| of the P90-breach rate against its nominal 10% needed to move coverage
    cov_up=0.15, cov_down=0.05,  # largest move of the coverage target in one change
    cov_floor=0.50, cov_cap=0.99,
    vol_gate=0.20,               # relative volatility difference to the tier needed before the buffer moves
    buf_ratio=(0.8, 1.5), buf_floor=0.05, buf_cap=0.30,
    min_alerts=6,                # alert-days needed before thresholds move
    prior_strength=10.0,         # pseudo-alerts at the network precision (shrinkage)
    thr_shift=10.0,              # largest move (risk % points) of the HIGH/WATCH thresholds
    thr_min_shift=4.0,
    watch_floor=10.0, high_cap=80.0, min_gap=10.0,
    cooldown_days=7,
)
PARAMS = ("coverage_prob", "buffer_frac", "high_threshold", "watch_threshold")
NOMINAL_BREACH = 0.10            # share of days a calibrated P90 should be exceeded


def breach_z(rate: float, n: int, p0: float = NOMINAL_BREACH) -> float:
    if n <= 0:
        return 0.0
    return (rate - p0) / math.sqrt(p0 * (1 - p0) / n)


def shrunk_precision(hits: int, alerts: int, prior: float, strength: float) -> float:
    return (hits + strength * prior) / (alerts + strength)


def network_context(profiles: list[dict], tiers: dict[str, str]) -> dict:
    """Network-wide reference values from every agent's profile (same date, same data cut)."""
    alerts = sum(p["alert_n"] for p in profiles)
    hits = sum(p["alert_hits"] for p in profiles)
    vols: dict[str, list[float]] = {}
    for p in profiles:
        if p.get("vol") is not None:
            vols.setdefault(tiers[p["agent_id"]], []).append(p["vol"])
    allv = [v for vs in vols.values() for v in vs]
    return dict(precision=max(0.02, hits / alerts) if alerts else 0.2, alerts=alerts,
                vol_by_tier={t: median(v) for t, v in vols.items() if len(v) >= 2}, vol_all=median(allv) if allv else None)


def propose(profile: dict, base: dict, net: dict, guard: dict = GUARD) -> dict:
    """Desired per-agent settings (only those that differ from `base`) with reasons.
    base: {coverage_prob, buffer_frac, high_threshold, watch_threshold} the agent would otherwise use (tier / global).
    Returns {"values": {param: value}, "reasons": [{code, params, text}]}."""
    values: dict[str, float] = {}
    reasons: list[dict] = []
    g = guard

    # 1. coverage: is the model's P90 exceeded far more (or far less) often than the nominal 10% for this agent?
    n, br_ = profile["n_obs"], profile["breaches"]
    if profile["n_days"] >= g["min_days"] and n >= g["min_days"]:
        rate = br_ / n
        z = breach_z(rate, n)
        if z >= g["z_gate"]:
            delta = min(g["cov_up"], 0.03 * z)
        elif z <= -g["z_gate"]:
            delta = -min(g["cov_down"], 0.02 * abs(z))
        else:
            delta = 0.0
        to = min(g["cov_cap"], max(g["cov_floor"], round(base["coverage_prob"] + delta, 3)))
        if abs(to - base["coverage_prob"]) >= 0.01:
            values["coverage_prob"] = to
            code = "coverage_up" if to > base["coverage_prob"] else "coverage_down"
            reasons.append(dict(code=code, params=dict(rate=round(100 * rate, 1), nominal=100 * NOMINAL_BREACH, n=n, breaches=br_, z=round(z, 2),
                                                       frm=round(100 * base["coverage_prob"], 1), to=round(100 * to, 1)),
                                text=f"coverage {100 * base['coverage_prob']:.1f}% -> {100 * to:.1f}%: demand exceeded the model's P90 on {br_} of {n} flow-days "
                                     f"({100 * rate:.0f}% against a nominal 10%, z={z:.1f})"))

    # 2. buffer: volatile agents (relative to their tier) keep a larger safety buffer, steady ones a smaller one
    vol_ref = net["vol_by_tier"].get(profile.get("tier")) or net["vol_all"]
    if profile["n_days"] >= g["min_days"] and profile.get("vol") is not None and vol_ref:
        ratio = profile["vol"] / vol_ref
        if abs(ratio - 1.0) >= g["vol_gate"]:
            lo, hi = g["buf_ratio"]
            to = min(g["buf_cap"], max(g["buf_floor"], round(base["buffer_frac"] * min(hi, max(lo, ratio)), 3)))
            if abs(to - base["buffer_frac"]) >= 0.01:
                values["buffer_frac"] = to
                reasons.append(dict(code="buffer_up" if to > base["buffer_frac"] else "buffer_down",
                                    params=dict(vol=round(profile["vol"], 3), ref=round(vol_ref, 3), ratio=round(ratio, 2),
                                                frm=round(100 * base["buffer_frac"], 1), to=round(100 * to, 1)),
                                    text=f"buffer {100 * base['buffer_frac']:.0f}% -> {100 * to:.0f}%: day-to-day volatility is {ratio:.2f}x that of comparable agents"))

    # 3. thresholds: alert earlier for agents whose warnings usually come true, later for those whose warnings rarely do
    if profile["alert_n"] >= g["min_alerts"]:
        prior = net["precision"]
        prec = shrunk_precision(profile["alert_hits"], profile["alert_n"], prior, g["prior_strength"])
        shift = -max(-g["thr_shift"], min(g["thr_shift"], 10.0 * math.log2(prec / prior)))
        if abs(shift) >= g["thr_min_shift"]:
            high = min(g["high_cap"], max(g["watch_floor"] + g["min_gap"], round(base["high_threshold"] + shift, 1)))
            watch = min(high - g["min_gap"], max(g["watch_floor"], round(base["watch_threshold"] + shift, 1)))
            if high != base["high_threshold"] or watch != base["watch_threshold"]:
                values["high_threshold"], values["watch_threshold"] = high, watch
                reasons.append(dict(code="thresholds_earlier" if shift < 0 else "thresholds_later",
                                    params=dict(hits=profile["alert_hits"], alerts=profile["alert_n"], precision=round(100 * prec, 0), network=round(100 * prior, 0),
                                                frm_high=base["high_threshold"], to_high=high, frm_watch=base["watch_threshold"], to_watch=watch),
                                    text=f"alert thresholds {base['watch_threshold']:.0f}/{base['high_threshold']:.0f}% -> {watch:.0f}/{high:.0f}%: "
                                         f"{profile['alert_hits']} of {profile['alert_n']} past alerts were followed by a stock-out "
                                         f"({100 * prec:.0f}% shrunk estimate against {100 * prior:.0f}% network-wide)"))
    return dict(values=values, reasons=reasons)
