"""Distributor routes (pure functions, no I/O).

Each division has one depot and a few vehicles. Given the day's approved order sizes, build for every vehicle an ordered list of
stops that is short AND serves the urgent agents first:
    cost(route) = distance_km + LAMBDA * sum( priority_weight_i * arrival_hours_i )
(an emergency stop weighs 3, a HIGH-risk one 2, others 1), minimised by nearest-neighbour construction followed by 2-opt and
or-opt local search. Stops are split between vehicles by a sweep around the depot, filling each vehicle up to its cash limit
(cash deliveries are carried out from the depot; cash collected from e-float top-ups comes back with the vehicle). If the day is
too short, the lowest-priority stops are dropped and reported, never silently. Straight-line (haversine) distance and an average
speed stand in for the road network; replace `dist_km` with a road-distance lookup when upay supplies one.
Recommendations only: a person approves the orders and may override any stop.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

LAMBDA = 2.0                      # km of extra driving accepted to save one priority-weighted hour of waiting
DEFAULT_ROUTING = dict(
    vehicles_per_division=1,      # vehicles that can leave each division's depot per day
    vehicle_cash_limit=300_000.0, # BDT of physical cash one vehicle may carry out
    speed_kmh=25.0,               # average road speed (placeholder)
    service_minutes=20.0,         # time at each agent
    day_hours=8.0,                # latest return to the depot
)
ROUTING_BOUNDS = dict(vehicles_per_division=(1, 20), vehicle_cash_limit=(10_000.0, 100_000_000.0), speed_kmh=(5.0, 120.0), service_minutes=(1.0, 120.0), day_hours=(1.0, 24.0))


def validate_routing(patch: dict, current: dict) -> dict:
    merged = {**current, **patch}
    if set(merged) != set(DEFAULT_ROUTING):
        raise ValueError(f"routing settings must be exactly: {', '.join(DEFAULT_ROUTING)}")
    for k, (lo, hi) in ROUTING_BOUNDS.items():
        v = merged[k]
        if not isinstance(v, (int, float)) or isinstance(v, bool) or not math.isfinite(v) or not (lo <= v <= hi):
            raise ValueError(f"{k} must be a number between {lo:g} and {hi:g}")
    merged["vehicles_per_division"] = int(merged["vehicles_per_division"])
    return {k: (v if k == "vehicles_per_division" else float(v)) for k, v in merged.items()}


def dist_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    la1, lo1, la2, lo2 = map(math.radians, (a[0], a[1], b[0], b[1]))
    h = math.sin((la2 - la1) / 2) ** 2 + math.cos(la1) * math.cos(la2) * math.sin((lo2 - lo1) / 2) ** 2
    return 2 * 6371.0 * math.asin(math.sqrt(h))


@dataclass
class Stop:
    key: str
    agent_id: str
    kind: str                     # cash | efloat
    lat: float
    lon: float
    amount: float
    weight: float = 1.0           # priority weight (emergency 3, HIGH 2, other 1)

    @property
    def pos(self) -> tuple[float, float]:
        return (self.lat, self.lon)

    @property
    def cash_out(self) -> float:
        return self.amount if self.kind == "cash" else 0.0


def evaluate(order: list[Stop], depot: tuple[float, float], s: dict) -> dict:
    """Distance, duration and priority-weighted arrival hours of visiting `order` from the depot and back."""
    t, d, pen, pos = 0.0, 0.0, 0.0, depot
    etas, legs = [], []
    for st in order:
        leg = dist_km(pos, st.pos)
        d += leg
        t += leg / s["speed_kmh"] * 60.0
        etas.append(t)
        legs.append(leg)
        pen += st.weight * t / 60.0
        t += s["service_minutes"]
        pos = st.pos
    back = dist_km(pos, depot) if order else 0.0
    d += back
    t += back / s["speed_kmh"] * 60.0
    return dict(distance_km=d, duration_min=t, weighted_hours=pen, cost=d + LAMBDA * pen, etas=etas, legs=legs, back_km=back)


def _nearest_neighbour(stops: list[Stop], depot: tuple[float, float]) -> list[Stop]:
    left, out, pos = list(stops), [], depot
    while left:
        # urgent stops pull a stop earlier: distance divided by weight
        nxt = min(left, key=lambda x: dist_km(pos, x.pos) / x.weight)
        out.append(nxt)
        left.remove(nxt)
        pos = nxt.pos
    return out


def _improve(order: list[Stop], depot: tuple[float, float], s: dict, max_pass: int = 30) -> list[Stop]:
    best, bc = order, evaluate(order, depot, s)["cost"]
    for _ in range(max_pass):
        improved = False
        n = len(best)
        for i in range(n - 1):                                       # 2-opt: reverse a segment
            for j in range(i + 1, n):
                cand = best[:i] + best[i:j + 1][::-1] + best[j + 1:]
                c = evaluate(cand, depot, s)["cost"]
                if c < bc - 1e-9:
                    best, bc, improved = cand, c, True
        for i in range(n):                                           # or-opt: move one stop elsewhere
            for j in range(n):
                if i == j:
                    continue
                cand = best[:i] + best[i + 1:]
                cand.insert(j, best[i])
                c = evaluate(cand, depot, s)["cost"]
                if c < bc - 1e-9:
                    best, bc, improved = cand, c, True
        if not improved:
            break
    return best


def _split(stops: list[Stop], depot: tuple[float, float], s: dict) -> tuple[list[list[Stop]], list[tuple[Stop, str]]]:
    """Sweep around the depot, filling each vehicle up to its cash limit; the rest cannot be carried today."""
    if not stops:
        return [], []
    top = max(stops, key=lambda x: x.weight)
    a0 = math.atan2(top.lat - depot[0], top.lon - depot[1])
    ordered = sorted(stops, key=lambda x: (math.atan2(x.lat - depot[0], x.lon - depot[1]) - a0) % (2 * math.pi))
    groups: list[list[Stop]] = [[]]
    load = 0.0
    unrouted: list[tuple[Stop, str]] = []
    for st in ordered:
        if st.cash_out > s["vehicle_cash_limit"]:
            unrouted.append((st, "over_capacity"))
            continue
        if load + st.cash_out > s["vehicle_cash_limit"] and groups[-1]:
            if len(groups) >= s["vehicles_per_division"]:
                unrouted.append((st, "no_vehicle"))
                continue
            groups.append([])
            load = 0.0
        groups[-1].append(st)
        load += st.cash_out
    return groups, unrouted


def plan_division(depot: tuple[float, float], stops: list[Stop], s: dict) -> dict:
    """Routes for one division's stops. Returns routes, unrouted stops with reasons, and the saving against visiting in agent-id order."""
    groups, unrouted = _split(stops, depot, s)
    groups = [g for g in groups if g]
    # balance: when several vehicles are allowed but the cash limit never forced a split, spread stops by sweep order
    if len(groups) == 1 and s["vehicles_per_division"] > 1 and len(groups[0]) > 1:
        k = min(s["vehicles_per_division"], len(groups[0]))
        flat = groups[0]
        size = math.ceil(len(flat) / k)
        groups = [flat[i:i + size] for i in range(0, len(flat), size)]
    routes, naive_km, naive_min = [], 0.0, 0.0
    limit = s["day_hours"] * 60.0
    for vi, g in enumerate(groups, 1):
        naive = evaluate(sorted(g, key=lambda x: x.agent_id), depot, s)
        naive_km += naive["distance_km"]
        order = _improve(_nearest_neighbour(g, depot), depot, s)
        ev = evaluate(order, depot, s)
        while order and ev["duration_min"] > limit:                  # the day is too short: drop the cheapest-to-lose stop, and say so
            drop = min(order, key=lambda x: (x.weight, -evaluate([y for y in order if y is not x], depot, s)["distance_km"]))
            unrouted.append((drop, "no_time"))
            order = [y for y in order if y is not drop]
            order = _improve(order, depot, s)
            ev = evaluate(order, depot, s)
        naive_min += naive["duration_min"]
        routes.append(dict(vehicle=vi, distance_km=ev["distance_km"], duration_min=ev["duration_min"], cash_out=sum(x.cash_out for x in order),
                           cash_in=sum(x.amount for x in order if x.kind == "efloat"), naive_km=naive["distance_km"],
                           stops=[dict(key=x.key, agent_id=x.agent_id, kind=x.kind, amount=x.amount, weight=x.weight, lat=x.lat, lon=x.lon,
                                       eta_min=ev["etas"][i], leg_km=ev["legs"][i]) for i, x in enumerate(order)]))
    used_km = sum(r["distance_km"] for r in routes)
    return dict(routes=routes, unrouted=[dict(key=x.key, agent_id=x.agent_id, kind=x.kind, amount=x.amount, reason=why) for x, why in unrouted],
                distance_km=used_km, naive_km=naive_km, saving_km=max(0.0, naive_km - used_km))
