"""Unit economics of replenishment: distributor trip cost vs the value of an unserved transaction, per agent tier.

Everything here is arithmetic on the policy-replay outcomes (data/policy_outcomes.json, built offline by ml_train from the
ledger with NO ground truth). The replay outcomes do not depend on any price, so changing an assumption re-optimises instantly.

Cost of a policy for a tier =
    trips        : trip_cost[tier] x orders
  + lost sales   : unserved BDT x margin_rate x customer_multiplier      (split: agent_share to the agent, the rest to upay)
  + capital      : average extra float the model's level needs beyond what the agent holds x capital_cost_annual x days / 365

All inputs are ASSUMPTIONS until upay supplies real trip costs and commission schedules; the page says so.
"""
from __future__ import annotations

import json
import math
from functools import lru_cache
from pathlib import Path

OUTCOMES_PATH = Path(__file__).resolve().parents[1] / "data" / "policy_outcomes.json"
TIERS = ("garment_urban", "market_urban", "remittance_urban", "rural", "university_urban")

DEFAULT_ECONOMICS = dict(
    trip_cost={"garment_urban": 150.0, "market_urban": 150.0, "remittance_urban": 150.0, "university_urban": 150.0, "rural": 300.0},  # BDT per order
    margin_rate=0.01,             # share of a transaction's value earned (agent + upay) = what an unserved transaction costs
    agent_share=0.70,             # share of that margin that goes to the agent
    customer_multiplier=1.0,      # >1: an unserved customer is worth more than one transaction (churn, goodwill)
    capital_cost_annual=0.12,     # yearly cost of extra capital the agent would need
)
ECON_BOUNDS = dict(margin_rate=(0.0005, 0.10), agent_share=(0.0, 1.0), customer_multiplier=(0.5, 50.0), capital_cost_annual=(0.0, 1.0))
TRIP_BOUNDS = (1.0, 5000.0)


def validate_economics(patch: dict, current: dict) -> dict:
    merged = {**current, **patch}
    for k, (lo, hi) in ECON_BOUNDS.items():
        v = merged[k]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not (lo <= v <= hi):
            raise ValueError(f"{k} must be a number between {lo} and {hi}")
    tc = merged["trip_cost"]
    if not isinstance(tc, dict) or set(tc) != set(TIERS):
        raise ValueError(f"trip_cost needs one value per tier: {', '.join(TIERS)}")
    for t, v in tc.items():
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not (TRIP_BOUNDS[0] <= v <= TRIP_BOUNDS[1]):
            raise ValueError(f"trip_cost for {t} must be between {TRIP_BOUNDS[0]:.0f} and {TRIP_BOUNDS[1]:.0f} BDT")
    return {**merged, "trip_cost": {t: float(tc[t]) for t in TIERS}}


@lru_cache(maxsize=1)
def outcomes() -> dict | None:
    if not OUTCOMES_PATH.exists():
        return None
    o = json.loads(OUTCOMES_PATH.read_text(encoding="utf-8"))
    agents = o["agents"]
    tier_idx = {t: [i for i, a in enumerate(agents) if o["tiers"][a] == t] for t in TIERS}
    o["_tier_idx"] = tier_idx
    for c in o["configs"]:                     # aggregate per tier once
        c["_tier"] = {t: dict(orders=sum(c["orders"][i] for i in ix), unserved=sum(c["unserved"][i] for i in ix),
                              demand=sum(c["demand"][i] for i in ix), stockout_days=sum(c["stockout_days"][i] for i in ix),
                              gap=sum(c["gap_avg"][i] for i in ix)) for t, ix in tier_idx.items()}
    return o


def _key(c) -> tuple:
    return (c["policy"], c["coverage"], c["buffer"], c["up"])


def tier_cost(c: dict, tier: str, e: dict, days: int) -> dict:
    a = c["_tier"][tier]
    trips = e["trip_cost"][tier] * a["orders"]
    lost_margin = a["unserved"] * e["margin_rate"] * e["customer_multiplier"]
    capital = a["gap"] * e["capital_cost_annual"] * days / 365.0
    return dict(orders=a["orders"], unserved=a["unserved"], demand=a["demand"], stockout_days=a["stockout_days"],
                service_rate=1.0 - a["unserved"] / max(a["demand"], 1.0), trips_cost=trips, lost_cost=lost_margin,
                lost_agent=lost_margin * e["agent_share"], lost_upay=lost_margin * (1 - e["agent_share"]), capital_cost=capital,
                total=trips + lost_margin + capital)


def _applied_cost(hy, current, t, row):
    """Cost of the settings the admin has applied, if they sit on the replayed grid (otherwise None: not evaluated)."""
    if not current or t not in current:
        return None
    k = (current[t]["coverage"], current[t]["buffer"], current[t]["up"])
    c = next((c for c in hy if (c["coverage"], c["buffer"], c["up"]) == k), None)
    return row(c, t) if c else None


def _hybrids(o):
    return [c for c in o["configs"] if c["policy"] == "hybrid"]


def analyse(e: dict, current: dict | None = None) -> dict:
    """Full ROI view for the given assumptions. `current`: {tier: {coverage, buffer, up}} the admin has applied (optional)."""
    o = outcomes()
    if o is None:
        return dict(available=False)
    days = o["period"]["days"]
    habit = next(c for c in o["configs"] if c["policy"] == "habit")
    hy = _hybrids(o)
    default_cfg = next(c for c in hy if c["coverage"] == 0.95 and c["buffer"] == 0.10 and c["up"] == 1.0)
    model_only = next(c for c in o["configs"] if c["policy"] == "model_only" and c["coverage"] == 0.95)

    def row(c, tier):
        return tier_cost(c, tier, e, days)

    tiers = {}
    for t in TIERS:
        base = row(habit, t)
        best = min(hy, key=lambda c: row(c, t)["total"])
        d95 = row(default_cfg, t)
        b = row(best, t)
        # break-even for the 95% hybrid vs habit: trip cost at which the extra trips exactly pay for the saved margin
        d_orders, d_unserved = d95["orders"] - base["orders"], base["unserved"] - d95["unserved"]
        saved_margin = d_unserved * e["margin_rate"] * e["customer_multiplier"]
        be_trip = saved_margin / d_orders if d_orders > 0 else None
        be_mult = (d_orders * e["trip_cost"][t]) / max(d_unserved * e["margin_rate"], 1e-9) if d_orders > 0 else None
        curve = []
        for p in o["grid"]["coverage"]:
            at_p = [c for c in hy if c["coverage"] == p]
            dflt = next(c for c in at_p if c["buffer"] == 0.10 and c["up"] == 1.0)
            bst = min(at_p, key=lambda c: row(c, t)["total"])
            curve.append(dict(coverage=p, cost_default=row(dflt, t)["total"], cost_best=row(bst, t)["total"],
                              orders=row(dflt, t)["orders"], unserved=row(dflt, t)["unserved"], service_rate=row(dflt, t)["service_rate"]))
        tiers[t] = dict(
            agents=len(o["_tier_idx"][t]), habit=base, hybrid95=d95, optimum=dict(**b, coverage=best["coverage"], buffer=best["buffer"], up=best["up"]),
            net_benefit_95=base["total"] - d95["total"], net_benefit_optimum=base["total"] - b["total"],
            roi_95=(base["total"] - d95["total"]) / max(d95["trips_cost"] - base["trips_cost"], 1.0) if d_orders > 0 else None,
            breakeven_trip_cost=be_trip, breakeven_multiplier=be_mult, curve=curve,
            model_only95=row(model_only, t),
            applied=(current or {}).get(t),
            applied_cost=_applied_cost(hy, current, t, row),
        )

    def network(c_for_tier):
        tot = dict(orders=0, unserved=0, demand=0, stockout_days=0, total=0, trips_cost=0, lost_cost=0, lost_agent=0, lost_upay=0, capital_cost=0)
        for t in TIERS:
            r = row(c_for_tier(t), t)
            for k in tot:
                tot[k] += r[k]
        tot["service_rate"] = 1.0 - tot["unserved"] / max(tot["demand"], 1.0)
        return tot

    habit_net = network(lambda t: habit)
    d95_net = network(lambda t: default_cfg)
    opt = {t: next(c for c in hy if (c["coverage"], c["buffer"], c["up"]) == (tiers[t]["optimum"]["coverage"], tiers[t]["optimum"]["buffer"], tiers[t]["optimum"]["up"])) for t in TIERS}
    opt_net = network(lambda t: opt[t])
    mo_net = network(lambda t: model_only)
    policies = dict(habit=habit_net, hybrid95=d95_net, optimum=opt_net, model_only95=mo_net)
    for k, v in policies.items():
        v["net_benefit"] = habit_net["total"] - v["total"]
    # sensitivity: network-wide best single hybrid configuration as trip cost and customer value vary
    sens = []
    for ts in (0.25, 0.5, 1.0, 2.0):
        for m in (1.0, 2.0, 5.0, 10.0, 20.0):
            e2 = {**e, "customer_multiplier": m, "trip_cost": {t: v * ts for t, v in e["trip_cost"].items()}}
            tot = lambda c, e2=e2: sum(tier_cost(c, t, e2, days)["total"] for t in TIERS)
            bc = min(hy, key=tot)
            sens.append(dict(trip_scale=ts, multiplier=m, coverage=bc["coverage"], buffer=bc["buffer"], up=bc["up"],
                             net_benefit=tot(habit) - tot(bc), beats_habit=tot(bc) < tot(habit)))
    verdict = "model_guided_pays" if policies["optimum"]["net_benefit"] > 0 else "habit_is_cheaper"
    return dict(available=True, stamp=o["stamp"], period=o["period"], assumptions=e, tiers=tiers, policies=policies, sensitivity=sens, verdict=verdict,
                calibration=o.get("calibration"), notebook_reference=o.get("notebook_reference"), grid=o["grid"],
                optimum_params={t: dict(coverage=tiers[t]["optimum"]["coverage"], buffer=tiers[t]["optimum"]["buffer"], up=tiers[t]["optimum"]["up"]) for t in TIERS})


def optimum_params(e: dict | None = None) -> dict | None:
    """{tier: {coverage, buffer, up}} cost-optimal under the assumptions (None if the replay file is not built)."""
    a = analyse(e or DEFAULT_ECONOMICS)
    return a.get("optimum_params") if a.get("available") else None
