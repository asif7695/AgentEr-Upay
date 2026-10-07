"""Network-wide allocation: solver properties on synthetic candidates, then the API (admin only, locks, budgets, approve)."""
import numpy as np
import pytest

from app.rules import allocation_rules as ar

V, LAM = 0.01, 0.0023
SETTINGS = dict(cash_budget=1e9, efloat_budget=1e9, max_orders_per_division=50, protect_high_risk=True)


def cand(key, kind="cash", division="Dhaka", cash=0.0, ef=100_000.0, peak_c=100_000.0, peak_e=0.0, trip=150.0, cap=200_000.0, rule=50_000.0, status="OK", protect=False):
    agent = key.split(":")[0]
    grid = np.linspace(0.5, 1.5, 201)
    c = ar.Candidate(key=key, agent_id=agent, kind=kind, division=division, tier="rural", cash=cash, efloat=ef, cap_cash=cap, cap_efloat=cap,
                     peak_cash=peak_c * grid, peak_efloat=peak_e * grid, buffer_cash=0.0, buffer_efloat=0.0, rule_amount=rule, trip_cost=trip,
                     min_order=0.1 * cap)
    c.status, c.protect = status, protect
    ar.prepare(c, V, LAM)
    return c


def net_cash(cands, amounts):
    return sum(amounts[c.key] * (1 if c.kind == "cash" else -1) for c in cands)


def test_value_curve_is_concave_and_orders_reduce_unserved():
    c = cand("A01:cash")
    assert np.all(np.diff(c.seg_m) <= 1e-9)
    assert ar.unserved(c, 40_000) < ar.unserved(c, 0)
    assert ar.unserved(c, 40_000) >= 0


def test_unconstrained_solution_orders_only_when_worth_a_trip():
    big = cand("A01:cash", peak_c=100_000)
    tiny = cand("A02:cash", peak_c=3_000, cash=0.0)             # a few thousand BDT of demand: lost margin < trip cost
    out = ar.solve([big, tiny], SETTINGS)
    assert out["status"] == "optimal" and out["amounts"]["A01:cash"] > 0 and out["amounts"]["A02:cash"] == 0


def test_cash_budget_and_trip_limits_are_respected():
    cands = [cand(f"A{i:02d}:cash", division="Dhaka" if i < 4 else "Sylhet", peak_c=90_000 + 5_000 * i) for i in range(1, 7)]
    for budget in (0.0, 40_000.0, 120_000.0):
        s = {**SETTINGS, "cash_budget": budget, "max_orders_per_division": 2}
        out = ar.solve(cands, s)
        assert out["status"] == "optimal"
        assert net_cash(cands, out["amounts"]) <= budget + 1e-6
        for div in ("Dhaka", "Sylhet"):
            assert sum(1 for c in cands if c.division == div and out["amounts"][c.key] > 0) <= 2
    assert ar.metrics(cands, ar.solve(cands, SETTINGS)["amounts"], V, LAM, SETTINGS)["feasible"]


def test_more_budget_never_costs_more():
    cands = [cand(f"A{i:02d}:cash", division=f"D{i}", peak_c=100_000 + 10_000 * i) for i in range(1, 6)]
    costs = []
    for b in (0, 50_000, 100_000, 200_000, 400_000):
        s = {**SETTINGS, "cash_budget": float(b)}
        costs.append(ar.metrics(cands, ar.solve(cands, s)["amounts"], V, LAM, s)["total_cost"])
    assert all(a >= b - 1.0 for a, b in zip(costs, costs[1:]))


def test_efloat_order_can_fund_a_cash_order():
    a = cand("A01:cash", peak_c=120_000, cash=0.0, ef=200_000, rule=60_000)
    b = cand("A02:efloat", kind="efloat", division="Sylhet", cash=150_000, ef=0.0, peak_c=0.0, peak_e=12_000, trip=150.0, rule=0.0)
    s = {**SETTINGS, "cash_budget": 0.0}
    alone = ar.solve([a], s)["amounts"]["A01:cash"]
    both = ar.solve([a, b], s)
    assert alone == 0
    assert both["amounts"]["A01:cash"] > 0 and both["amounts"]["A02:efloat"] > 0 and net_cash([a, b], both["amounts"]) <= 1e-6


def test_locks_are_honoured_and_infeasible_locks_are_reported():
    a, b = cand("A01:cash", peak_c=100_000), cand("A02:cash", division="Sylhet", peak_c=100_000)
    out = ar.solve([a, b], SETTINGS, locks={"A01:cash": 0.0, "A02:cash": 33_300.0})
    assert out["amounts"]["A01:cash"] == 0 and out["amounts"]["A02:cash"] == pytest.approx(33_300.0)
    s = {**SETTINGS, "cash_budget": 10_000.0}
    assert ar.solve([a, b], s, locks={"A01:cash": 50_000.0})["status"] == "infeasible"


def test_high_risk_agents_are_protected_unless_impossible():
    low_value = cand("A01:cash", peak_c=4_000, cash=0.0, status="HIGH", protect=True)
    assert ar.solve([low_value], SETTINGS)["amounts"]["A01:cash"] > 0
    assert ar.solve([low_value], SETTINGS, protect=False)["amounts"]["A01:cash"] == 0
    no_stock = cand("A02:cash", peak_c=4_000, ef=0.0, status="HIGH", protect=True)             # nothing to convert: physically impossible
    assert no_stock.xmax == 0 and ar.solve([no_stock], SETTINGS)["amounts"]["A02:cash"] == 0
    s = {**SETTINGS, "cash_budget": 0.0}
    assert ar.solve([low_value], s)["status"] == "infeasible"                                      # protection cannot beat a zero budget: the service relaxes it


def test_simple_plan_respects_limits_and_orders_by_risk():
    cs = [cand("A01:cash", rule=60_000, status="HIGH"), cand("A02:cash", rule=60_000, status="OK")]
    cs[0].risk_pct, cs[1].risk_pct = 90.0, 20.0
    out = ar.simple_plan(cs, {**SETTINGS, "cash_budget": 70_000.0})
    assert out["A01:cash"] == 60_000.0 and out["A02:cash"] == 0.0           # the 10,000 left is below the minimum order: no trip
    assert net_cash(cs, out) <= 70_000.0


def test_validate_allocation():
    ok = ar.validate_allocation({"cash_budget": 5000}, ar.DEFAULT_ALLOCATION)
    assert ok["cash_budget"] == 5000.0 and ok["max_orders_per_division"] == 2
    for bad in ({"cash_budget": -1}, {"max_orders_per_division": 1000}, {"protect_high_risk": "yes"}, {"efloat_budget": float("nan")}):
        with pytest.raises(ValueError):
            ar.validate_allocation(bad, ar.DEFAULT_ALLOCATION)


# --------------------------------------------------------------------------- API
def test_plan_is_admin_only_feasible_and_has_no_ground_truth(client, admin, agent_a01):
    assert client.get("/admin/allocation", headers=agent_a01).status_code == 403
    r = client.get("/admin/allocation", headers=admin)
    assert r.status_code == 200
    p = r.json()
    for k in ("true_cashout", "unserved_cash", "base_cashout", "noise_std"):
        assert k not in r.text
    assert p["totals"]["optimised"]["feasible"] and p["totals"]["optimised"]["net_cash"] <= p["settings"]["cash_budget"]
    assert p["totals"]["optimised"]["total_cost"] <= p["totals"]["simple"]["total_cost"] + 1
    assert len(p["budget_curve"]) >= 5 and all(ln["amount"] <= ln["max_amount"] for ln in p["lines"])
    assert {"rule", "simple", "optimised", "nothing", "unconstrained"} <= set(p["totals"])


def test_settings_validation_audit_and_effect(client, admin):
    assert client.put("/admin/allocation/settings", json={"cash_budget": -5}, headers=admin).status_code == 422
    assert client.put("/admin/allocation/settings", json={}, headers=admin).status_code == 422
    r = client.put("/admin/allocation/settings", json={"cash_budget": 0, "max_orders_per_division": 1}, headers=admin)
    assert r.status_code == 200
    p = r.json()
    assert p["settings"]["cash_budget"] == 0 and p["totals"]["optimised"]["net_cash"] <= 0
    assert all(sum(1 for x in p["lines"] if x["division"] == div and x["amount"] > 0) <= 1 for div in {x["division"] for x in p["lines"]})
    assert client.get("/admin/config", headers=admin).json()["rules"]["allocation"]["cash_budget"] == 0
    assert "allocation_settings" in [a["action"] for a in client.get("/admin/audit?limit=20", headers=admin).json()]


def test_locks_and_what_if_do_not_persist(client, admin):
    base = client.get("/admin/allocation", headers=admin).json()
    key = next(ln["key"] for ln in base["lines"] if ln["amount"] > 0)
    p = client.post("/admin/allocation/solve", json={"locks": {key: 0}}, headers=admin).json()
    assert next(ln for ln in p["lines"] if ln["key"] == key)["amount"] == 0 and next(ln for ln in p["lines"] if ln["key"] == key)["locked"]
    assert client.post("/admin/allocation/solve", json={"locks": {"A99:cash": 5}}, headers=admin).status_code == 422
    assert client.post("/admin/allocation/solve", json={"locks": {key: -5}}, headers=admin).status_code == 422
    w = client.post("/admin/allocation/solve", json={"settings": {"cash_budget": 1_000_000}}, headers=admin).json()
    assert w["settings"]["cash_budget"] == 1_000_000
    assert client.get("/admin/config", headers=admin).json()["rules"]["allocation"]["cash_budget"] == base["settings"]["cash_budget"]
    assert client.post("/admin/allocation/solve", json={"settings": {"cash_budget": -1}}, headers=admin).status_code == 422


def test_approve_creates_proposed_orders_once(client, admin, agent_a01):
    assert client.post("/admin/allocation/approve", json={}, headers=agent_a01).status_code == 403
    plan = client.get("/admin/allocation", headers=admin).json()
    wanted = {ln["key"]: ln["amount"] for ln in plan["lines"] if ln["amount"] > 0 and not ln["order"]}
    assert wanted
    r = client.post("/admin/allocation/approve", json={}, headers=admin)
    assert r.status_code == 200
    made = r.json()["created"]
    assert len(made) == len(wanted) and all(o["status"] == "proposed" and o["note"] == "Optimised plan" for o in made)
    assert {f"{o['agent_id']}:{o['kind']}": o["amount"] for o in made} == wanted
    again = client.post("/admin/allocation/approve", json={}, headers=admin).json()
    assert again["created"] == [] and len(again["skipped"]) == len(wanted)
    assert len([o for o in client.get("/admin/orders", headers=admin).json() if o["note"] == "Optimised plan"]) == len(wanted)
    assert "allocation_approve" in [a["action"] for a in client.get("/admin/audit?limit=50", headers=admin).json()]
