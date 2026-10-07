"""Network-wide replenishment allocation (pure functions, no I/O).

Question answered every day: given what the distributor can actually deliver, how much should each agent receive, and which
agents should not get a trip at all?

Value of an order of size x to an agent (all in BDT, over the 7-day forecast horizon):
    v * ( U(0) - U(x) )  -  capital_rate * x  -  trip_cost                (the trip cost only if x > 0)
where U(x) is the expected unserved demand when the order lifts one balance by x (and lowers the other: a cash top-up converts
e-float into cash, an e-float top-up buys e-float with cash). U comes from the same Monte Carlo paths as the risk numbers:
the peak cumulative net cash-out over the horizon M gives a cash shortfall (M - cash - x)+ and the mirror peak an e-float one.
U is convex in x, so the value is concave and a piecewise-linear MILP (scipy / HiGHS) solves the whole network exactly.

Constraints: the distributor's net physical cash and net e-float it can send per day (an e-float top-up brings cash back,
which funds cash top-ups), a trip limit per division, and the rule that orders below a minimum size are not worth a trip.
Recommendations only: a person approves, locks or overrides every line.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp

SEGMENTS = 12
ROUND_TO = 100.0
HORIZON_DAYS = 7

DEFAULT_ALLOCATION = dict(
    cash_budget=100_000.0,        # net physical cash the distributor can send out per day (cash top-ups minus cash collected from e-float top-ups)
    efloat_budget=150_000.0,      # net e-float it can send out per day (the mirror quantity)
    max_orders_per_division=2,    # trips (orders) one division can be served per day
    protect_high_risk=True,       # an agent at HIGH risk always gets a trip when physically possible, even if the placeholder economics say the lost margin is small
)
ALLOCATION_BOUNDS = dict(cash_budget=(0.0, 100_000_000.0), efloat_budget=(0.0, 100_000_000.0), max_orders_per_division=(0, 50))


def validate_allocation(patch: dict, current: dict) -> dict:
    merged = {**current, **patch}
    if set(merged) != set(DEFAULT_ALLOCATION):
        raise ValueError(f"allocation settings must be exactly: {', '.join(DEFAULT_ALLOCATION)}")
    if not isinstance(merged["protect_high_risk"], bool):
        raise ValueError("protect_high_risk must be true or false")
    for k, (lo, hi) in ALLOCATION_BOUNDS.items():
        v = merged[k]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not np.isfinite(v) or not (lo <= v <= hi):
            raise ValueError(f"{k} must be a number between {lo:g} and {hi:g}")
    merged["max_orders_per_division"] = int(merged["max_orders_per_division"])
    return {k: (float(v) if k in ("cash_budget", "efloat_budget") else v) for k, v in merged.items()}


@dataclass
class Candidate:
    key: str                  # "A01:cash"
    agent_id: str
    kind: str                 # cash (convert e-float to cash) | efloat (buy e-float with cash)
    division: str
    tier: str
    cash: float
    efloat: float
    cap_cash: float
    cap_efloat: float
    peak_cash: np.ndarray     # quantile grid of the 7-day peak net cash-out
    peak_efloat: np.ndarray   # quantile grid of the 7-day peak net cash-in (e-float drain)
    buffer_cash: float
    buffer_efloat: float
    rule_amount: float        # what the per-agent rule recommends (0 if nothing)
    trip_cost: float
    min_order: float
    xmax: float = 0.0
    risk_pct: float = 0.0
    status: str = "OK"
    protect: bool = False        # agent is at HIGH risk on this balance: a trip is mandatory whenever one is physically possible
    seg_w: np.ndarray = field(default_factory=lambda: np.zeros(0))
    seg_m: np.ndarray = field(default_factory=lambda: np.zeros(0))

    def sign(self) -> tuple[float, float]:
        return (1.0, -1.0) if self.kind == "cash" else (-1.0, 1.0)


def unserved(c: Candidate, x: float) -> float:
    """Expected unserved demand (BDT) over the horizon if this agent receives an order of size x of c.kind."""
    dc, de = c.sign()
    return float(np.mean(np.maximum(0.0, c.peak_cash - (c.cash + dc * x))) + np.mean(np.maximum(0.0, c.peak_efloat - (c.efloat + de * x))))


def baseline_unserved(c: Candidate) -> float:
    return unserved(c, 0.0)


def prepare(c: Candidate, v: float, lam: float) -> None:
    """Max order size and the concave piecewise-linear value curve."""
    if c.kind == "cash":
        room, avail = c.cap_cash - c.cash, c.efloat - c.buffer_efloat          # can only convert e-float the agent can spare
    else:
        room, avail = c.cap_efloat - c.efloat, c.cash - c.buffer_cash
    c.xmax = float(max(0.0, min(room, avail)))
    if c.xmax < max(c.min_order, 1.0):
        c.xmax = 0.0
        c.seg_w, c.seg_m = np.zeros(0), np.zeros(0)
        return
    xs = np.linspace(0.0, c.xmax, SEGMENTS + 1)
    u = np.array([unserved(c, x) for x in xs])
    w = np.diff(xs)
    gain = v * (u[:-1] - u[1:]) - lam * w
    c.seg_w, c.seg_m = w, gain / w


def value_of(c: Candidate, x: float, v: float, lam: float) -> float:
    """Net value (BDT) of ordering x: avoided lost margin - capital cost - trip cost."""
    if x <= 0:
        return 0.0
    return v * (unserved(c, 0.0) - unserved(c, x)) - lam * x - c.trip_cost


def solve(cands: list[Candidate], settings: dict, locks: dict[str, float] | None = None, relax: bool = False, protect: bool = True) -> dict:
    """Optimal order sizes. relax=True ignores the budgets and trip limits (used to tell 'low value' from 'no budget').
    Returns {"status": "optimal"|"infeasible", "amounts": {key: x}}."""
    locks = locks or {}
    live = [c for c in cands if c.xmax > 0 or c.key in locks]
    amounts = {c.key: 0.0 for c in cands}
    if not live:
        return dict(status="optimal", amounts=amounts)
    offs, n = {}, 0
    for c in live:
        offs[c.key] = n
        n += len(c.seg_w)
    nz = len(live)
    N = n + nz
    cost = np.zeros(N)
    ub = np.zeros(N)
    lb = np.zeros(N)
    for c in live:
        o = offs[c.key]
        cost[o:o + len(c.seg_w)] = -c.seg_m
        ub[o:o + len(c.seg_w)] = c.seg_w
    integrality = np.zeros(N)
    rows, lo, hi = [], [], []
    zi = {c.key: n + i for i, c in enumerate(live)}
    for c in live:
        z = zi[c.key]
        cost[z] = c.trip_cost
        ub[z] = 1.0
        integrality[z] = 1
        o, k = offs[c.key], len(c.seg_w)
        r = np.zeros(N)
        r[o:o + k] = 1.0
        r[z] = -c.xmax
        rows.append(r); lo.append(-np.inf); hi.append(0.0)                       # amount <= xmax * z
        if protect and c.protect and c.xmax > 0 and c.key not in locks:
            lb[z] = 1.0                                                        # HIGH-risk agent: always served when physically possible
        if c.key in locks:
            amt = float(min(max(locks[c.key], 0.0), c.xmax))
            lb[z] = ub[z] = 1.0 if amt > 0 else 0.0
            r2 = np.zeros(N)
            r2[o:o + k] = 1.0
            rows.append(r2); lo.append(amt); hi.append(amt)
        else:
            r3 = np.zeros(N)
            r3[o:o + k] = -1.0
            r3[z] = c.min_order
            rows.append(r3); lo.append(-np.inf); hi.append(0.0)                  # amount >= min_order * z
    if not relax:
        net = np.zeros(N)
        for c in live:
            o, k = offs[c.key], len(c.seg_w)
            net[o:o + k] = 1.0 if c.kind == "cash" else -1.0
        rows.append(net); lo.append(-np.inf); hi.append(settings["cash_budget"])        # net cash out
        rows.append(-net); lo.append(-np.inf); hi.append(settings["efloat_budget"])     # net e-float out
        for div in sorted({c.division for c in live}):
            r = np.zeros(N)
            for c in live:
                if c.division == div:
                    r[zi[c.key]] = 1.0
            rows.append(r); lo.append(-np.inf); hi.append(settings["max_orders_per_division"])
    res = milp(cost, constraints=LinearConstraint(np.array(rows), np.array(lo), np.array(hi)), integrality=integrality, bounds=Bounds(lb, ub),
               options=dict(mip_rel_gap=0.002, time_limit=5.0))
    if res.status != 0 or res.x is None:
        return dict(status="infeasible", amounts=amounts)
    for c in live:
        o, k = offs[c.key], len(c.seg_w)
        amounts[c.key] = float(np.floor(res.x[o:o + k].sum() / ROUND_TO) * ROUND_TO) if c.key not in locks else float(min(max(locks[c.key], 0.0), c.xmax))
    return dict(status="optimal", amounts=amounts)


def metrics(cands: list[Candidate], amounts: dict[str, float], v: float, lam: float, settings: dict | None = None) -> dict:
    """Totals for a set of order sizes: orders, net cash, expected unserved over ALL agents, and money."""
    by_agent: dict[str, dict] = {}
    for c in cands:
        a = by_agent.setdefault(c.agent_id, dict(cash=c.cash, ef=c.efloat, peak_c=c.peak_cash, peak_e=c.peak_efloat))
    orders = trip = capital = 0.0
    net_cash = 0.0
    for c in cands:
        x = amounts.get(c.key, 0.0)
        if x > 0:
            orders += 1
            trip += c.trip_cost
            capital += lam * x
            net_cash += x if c.kind == "cash" else -x
            dc, de = c.sign()
            by_agent[c.agent_id]["cash"] += dc * x
            by_agent[c.agent_id]["ef"] += de * x
    un = sum(float(np.mean(np.maximum(0.0, a["peak_c"] - a["cash"])) + np.mean(np.maximum(0.0, a["peak_e"] - a["ef"]))) for a in by_agent.values())
    out = dict(orders=int(orders), net_cash=net_cash, total_cash_orders=sum(amounts.get(c.key, 0.0) for c in cands if c.kind == "cash"),
               total_efloat_orders=sum(amounts.get(c.key, 0.0) for c in cands if c.kind == "efloat"), expected_unserved=un,
               trip_cost=trip, lost_cost=v * un, capital_cost=capital, total_cost=trip + v * un + capital)
    if settings is not None:
        divs: dict[str, int] = {}
        for c in cands:
            if amounts.get(c.key, 0.0) > 0:
                divs[c.division] = divs.get(c.division, 0) + 1
        out["feasible"] = bool(net_cash <= settings["cash_budget"] + 1e-6 and -net_cash <= settings["efloat_budget"] + 1e-6
                               and all(n <= settings["max_orders_per_division"] for n in divs.values()))
        out["cash_over_budget"] = max(0.0, net_cash - settings["cash_budget"])
    return out


def simple_plan(cands: list[Candidate], settings: dict) -> dict[str, float]:
    """What a dispatcher does without an optimiser: walk down the risk list (HIGH first), give each agent the amount the per-agent
    rule recommends, and stop when the cash budget or the division's trip limit runs out (a partial fill if it still makes a trip)."""
    order = sorted((c for c in cands if c.rule_amount > 0 and c.xmax > 0), key=lambda c: (c.status != "HIGH", -c.risk_pct, c.key))
    amounts = {c.key: 0.0 for c in cands}
    net, trips = 0.0, {}
    for c in order:
        x = min(c.rule_amount, c.xmax)
        if c.kind == "cash":
            x = min(x, settings["cash_budget"] - net)
        else:
            x = min(x, settings["efloat_budget"] + net)
        x = float(np.floor(x / ROUND_TO) * ROUND_TO)
        if x < max(c.min_order, 1.0) or trips.get(c.division, 0) >= settings["max_orders_per_division"]:
            continue
        amounts[c.key] = x
        trips[c.division] = trips.get(c.division, 0) + 1
        net += x if c.kind == "cash" else -x
    return amounts


def reason(c: Candidate, x: float, x_free: float, value: float = 0.0) -> str:
    r = c.rule_amount
    if x <= 0 and r <= 0:
        return "none"
    if x <= 0:
        return "skipped_low_value" if x_free <= 0 else "skipped_limits"
    if value < 0:
        return "protected" if c.protect else "funding"          # a loss-making trip is kept to protect a HIGH-risk agent, or to bring cash in that funds other orders
    if r <= 0:
        return "added"
    if x < 0.9 * r:
        return "reduced" if x_free < 0.9 * r else "reduced_limits"
    if x > 1.1 * r:
        return "increased"
    return "kept"
