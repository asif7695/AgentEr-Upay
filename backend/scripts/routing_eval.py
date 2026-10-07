"""Offline evidence for the route optimiser on a SCALED synthetic network (writes app/data/routing_eval.json).

The real dataset has two agents per division, which makes routing trivial. This test places 200 synthetic agents (25 per division,
urban 3-14 km and rural 15-45 km from the depot), gives each a random order, and compares the optimiser with visiting stops in
agent-id order and with a random order, for several fleet sizes. Run from backend/:  python -m scripts.routing_eval
"""
from __future__ import annotations

import json
import random
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.rules import routing as rt  # noqa: E402
from app.services import geo  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "routing_eval.json"


def network(seed: int, per_div: int = 25) -> dict[str, list[rt.Stop]]:
    rnd = random.Random(seed)
    by = {}
    for div in geo.DEPOTS:
        st = []
        for i in range(per_div):
            aid = f"{div[:2].upper()}{i:02d}"
            tier = "rural" if rnd.random() < 0.4 else "urban"
            la, lo = geo.agent_position(aid, div, tier)
            kind = "cash" if rnd.random() < 0.75 else "efloat"
            st.append(rt.Stop(f"{aid}:{kind}", aid, kind, la, lo, round(rnd.uniform(15_000, 90_000), -2), rnd.choice([1.0, 1.0, 1.0, 2.0, 3.0])))
        by[div] = st
    return by


def main():
    rows = []
    for vehicles in (1, 2, 4):
        s = {**rt.DEFAULT_ROUTING, "vehicles_per_division": vehicles, "day_hours": 24.0, "vehicle_cash_limit": 3_000_000.0}
        opt = naive = rnd_km = 0.0
        stops_n = unrouted = 0
        wh_opt = wh_naive = 0.0
        t0 = time.time()
        for seed in range(3):
            net = network(seed)
            for div, stops in net.items():
                dp = geo.depot(div)
                res = rt.plan_division(dp, stops, s)
                opt += res["distance_km"]
                naive += res["naive_km"]
                unrouted += len(res["unrouted"])
                stops_n += sum(len(r["stops"]) for r in res["routes"])
                for r in res["routes"]:
                    order = [next(x for x in stops if x.key == st["key"]) for st in r["stops"]]
                    wh_opt += rt.evaluate(order, dp, s)["weighted_hours"]
                    wh_naive += rt.evaluate(sorted(order, key=lambda x: x.agent_id), dp, s)["weighted_hours"]
                    shuffled = order[:]
                    random.Random(seed).shuffle(shuffled)
                    rnd_km += rt.evaluate(shuffled, dp, s)["distance_km"]
        rows.append(dict(vehicles_per_division=vehicles, stops=stops_n, unrouted=unrouted, optimised_km=round(opt), id_order_km=round(naive), random_order_km=round(rnd_km),
                         saving_vs_id_order_pct=round(100 * (1 - opt / naive), 1), saving_vs_random_pct=round(100 * (1 - opt / rnd_km), 1),
                         priority_waiting_saving_pct=round(100 * (1 - wh_opt / wh_naive), 1), seconds=round(time.time() - t0, 1)))
        print(rows[-1])
    OUT.write_text(json.dumps(dict(stamp="SYNTHETIC network: 200 agents (25 per division), 3 random draws, order sizes 15-90k BDT, priority weights 1-3.", rows=rows,
                                   rule="nearest-neighbour + 2-opt + or-opt on distance + 2 km per priority-weighted hour", baselines="id order = visiting agents in id order; random = shuffled"), indent=1), encoding="utf-8")
    print("written", OUT)


if __name__ == "__main__":
    main()
