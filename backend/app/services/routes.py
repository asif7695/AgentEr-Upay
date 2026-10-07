"""Routes for today's optimised plan: turns each division's approved-size lines into vehicle routes (rules/routing.py)."""
from __future__ import annotations

from datetime import date

from ..rules import routing as rt
from . import geo
from .allocation import plan as allocation_plan
from .context import Ctx, ledger


def build(ctx: Ctx, d: date, locks: dict[str, float] | None = None) -> dict:
    s = ctx.rules["routing"]
    p = allocation_plan(ctx, d, locks=locks, curve=False)
    by_div: dict[str, list[rt.Stop]] = {}
    for ln in p["lines"]:
        if ln["amount"] <= 0:
            continue
        a = ledger.agents[ln["agent_id"]]
        la, lo = geo.agent_position(ln["agent_id"], a["division"], a["location_type"])
        emergency = ln["status"] == "HIGH" and ln["late"]
        by_div.setdefault(a["division"], []).append(rt.Stop(ln["key"], ln["agent_id"], ln["kind"], la, lo, float(ln["amount"]), 3.0 if emergency else 2.0 if ln["status"] == "HIGH" else 1.0))
    divisions = []
    for div in sorted(by_div):
        dp = geo.depot(div)
        res = rt.plan_division(dp, by_div[div], s)
        divisions.append(dict(division=div, depot=dict(lat=dp[0], lon=dp[1]), **res))
    tot = lambda k: sum(x[k] for x in divisions)
    return dict(date=d.isoformat(), settings=s, bounds=rt.ROUTING_BOUNDS, divisions=divisions,
                totals=dict(distance_km=tot("distance_km"), naive_km=tot("naive_km"), saving_km=tot("saving_km"), stops=sum(len(r["stops"]) for x in divisions for r in x["routes"]),
                            vehicles=sum(len(x["routes"]) for x in divisions), unrouted=sum(len(x["unrouted"]) for x in divisions)),
                synthetic_geography=True,
                note="Positions are SYNTHETIC (the dataset has none): a depot at each divisional HQ and agents placed deterministically around it. Straight-line distance and an "
                     "average speed stand in for roads. Recommendations only; the orders are the ones approved in the Optimised plan.")
