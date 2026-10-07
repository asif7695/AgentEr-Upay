"""Unit economics / ROI: arithmetic, replay mechanics, optimum behaviour, per-tier rules, API."""
import json

import numpy as np
import pytest

from app.rules import business_rules as br
from app.rules import economics as ec

E = ec.DEFAULT_ECONOMICS


def test_cost_components_add_up():
    o = ec.outcomes()
    c = o["configs"][0]
    r = ec.tier_cost(c, "rural", E, o["period"]["days"])
    a = c["_tier"]["rural"]
    assert r["trips_cost"] == pytest.approx(E["trip_cost"]["rural"] * a["orders"])
    assert r["lost_cost"] == pytest.approx(a["unserved"] * E["margin_rate"] * E["customer_multiplier"])
    assert r["lost_agent"] + r["lost_upay"] == pytest.approx(r["lost_cost"]) and r["lost_agent"] == pytest.approx(r["lost_cost"] * E["agent_share"])
    assert r["total"] == pytest.approx(r["trips_cost"] + r["lost_cost"] + r["capital_cost"])
    assert 0 < r["service_rate"] <= 1


def test_economics_validation():
    assert ec.validate_economics({"margin_rate": 0.02}, E)["margin_rate"] == 0.02
    for bad in ({"margin_rate": -1}, {"agent_share": 2}, {"customer_multiplier": 0}, {"trip_cost": {"rural": 5}},
                {"trip_cost": {**E["trip_cost"], "rural": 1e9}}, {"margin_rate": float("nan")}):
        with pytest.raises(ValueError):
            ec.validate_economics(bad, E)


def test_replay_conserves_float_and_never_goes_negative():
    from ml_train import replay
    rng = np.random.default_rng(0)
    D, A = 60, 6
    co, ci = rng.uniform(5e3, 6e4, (D, A)), rng.uniform(5e3, 6e4, (D, A))
    working = rng.random(D + 8) > 0.3
    cap = np.full(A, 2e5)
    cash0, ef0 = np.full(A, 8e4), np.full(A, 9e4)
    req = np.full((D, A), 9e4)
    for pol in ("habit", "hybrid", "model_only"):
        r = replay.simulate(pol, co, ci, working, cap, cap, cash0, ef0, req_c=req, req_e=req, u=2.0, notice=rng.random((D, A)), q=0.6)
        assert np.allclose(r["final_total"], cash0 + ef0)            # a top-up only converts one balance into the other
        assert (r["min_balance"] >= -1e-6).all() and (r["unserved"] >= 0).all()


def test_replay_reproduces_the_ledger_and_the_notebook_ordering_without_ground_truth():
    o = ec.outcomes()
    cal = o["calibration"]
    habit = next(c for c in o["configs"] if c["policy"] == "habit")
    hy = next(c for c in o["configs"] if c["policy"] == "hybrid" and c["coverage"] == 0.95 and c["buffer"] == 0.10 and c["up"] == 1.0)
    assert abs(sum(habit["stockout_days"]) - cal["ledger_stockout_days"]) <= 8            # habit baseline matches the ledger's recorded stock-outs
    assert sum(hy["stockout_days"]) < 0.6 * sum(habit["stockout_days"]) and sum(hy["unserved"]) < 0.6 * sum(habit["unserved"])
    assert sum(hy["orders"]) > sum(habit["orders"])                                       # more trips: the cost side
    assert "true_" not in json.dumps({k: v for k, v in o.items() if k not in ("configs", "_tier_idx")})


def test_optimum_responds_sensibly_to_prices():
    base = ec.analyse(E)
    dear = ec.analyse({**E, "trip_cost": {t: v * 4 for t, v in E["trip_cost"].items()}})
    rich = ec.analyse({**E, "customer_multiplier": 20.0})
    assert dear["policies"]["optimum"]["orders"] <= base["policies"]["optimum"]["orders"]          # dearer trips -> fewer trips
    assert rich["policies"]["optimum"]["unserved"] <= base["policies"]["optimum"]["unserved"]      # more valuable customers -> fewer unserved
    assert base["policies"]["optimum"]["total"] <= base["policies"]["hybrid95"]["total"]           # the optimum is never worse than a fixed 95%
    for t, v in base["tiers"].items():
        assert v["optimum"]["coverage"] in ec.outcomes()["grid"]["coverage"]
    assert base["verdict"] in ("model_guided_pays", "habit_is_cheaper")
    assert {s["multiplier"] for s in base["sensitivity"]} == {1.0, 2.0, 5.0, 10.0, 20.0}


def test_breakeven_trip_cost_is_where_the_95_policy_stops_paying():
    t = "garment_urban"
    be = ec.analyse(E)["tiers"][t]["breakeven_trip_cost"]
    assert be and be > 0
    zero_capital = {**E, "capital_cost_annual": 0.0, "trip_cost": {**E["trip_cost"], t: be}}
    assert abs(ec.analyse(zero_capital)["tiers"][t]["net_benefit_95"]) < 1.0                       # net benefit crosses zero at the break-even


def test_topup_amount_rule():
    assert br.topup_amount(100.0, 40.0, 500.0, 1.0, 0.1) == 60.0
    assert br.topup_amount(100.0, 40.0, 500.0, 2.0, 0.1) == 160.0           # order up to 2x the required level
    assert br.topup_amount(400.0, 40.0, 500.0, 3.0, 0.1) == 460.0           # never above capacity
    assert br.topup_amount(100.0, 90.0, 500.0, 1.0, 0.1) == 0.0             # below the minimum order size


def test_per_tier_rules_reach_the_forecast_and_the_cache(client, admin):
    a01 = client.get("/agents/A01/forecast?explain=false", headers=admin).json()
    a02 = client.get("/agents/A02/forecast?explain=false", headers=admin).json()
    rules = client.get("/admin/config", headers=admin).json()["rules"]
    t1 = a01["agent"]["location_type"]
    assert a01["config"]["tier"] == t1 and a01["config"]["coverage_prob"] == rules["coverage_by_tier"][t1]
    assert client.put("/admin/config", json={"coverage_by_tier": {t1: 0.99}}, headers=admin).status_code == 200
    b = client.get("/agents/A01/forecast?explain=false", headers=admin).json()
    assert b["config"]["coverage_prob"] == 0.99 and b["cash"]["recommended_level"] >= a01["cash"]["recommended_level"]
    assert client.get("/agents/A02/forecast?explain=false", headers=admin).json()["config"]["coverage_prob"] == a02["config"]["coverage_prob"]
    assert client.put("/admin/config", json={"coverage_by_tier": {"nope": 0.9}}, headers=admin).status_code == 422
    assert client.put("/admin/config", json={"topup_mult_by_tier": {"rural": 9}}, headers=admin).status_code == 422


def test_changing_global_coverage_clears_tier_overrides_but_resaving_keeps_them(client, admin):
    rules = client.get("/admin/config", headers=admin).json()["rules"]
    assert rules["coverage_by_tier"]
    client.put("/admin/config", json={"coverage_prob": rules["coverage_prob"], "buffer_frac": rules["buffer_frac"]}, headers=admin)
    assert client.get("/admin/config", headers=admin).json()["rules"]["coverage_by_tier"] == rules["coverage_by_tier"]
    client.put("/admin/config", json={"coverage_prob": 0.9}, headers=admin)
    assert client.get("/admin/config", headers=admin).json()["rules"]["coverage_by_tier"] == {}


def test_economics_api_is_admin_only_validated_audited_and_apply_works(client, admin, agent_a01):
    assert client.get("/admin/economics", headers=agent_a01).status_code == 403
    assert client.get("/admin/economics").status_code == 401
    v = client.get("/admin/economics", headers=admin).json()
    assert v["available"] and set(v["tiers"]) == set(ec.TIERS) and v["policies"]["habit"]["net_benefit"] == 0
    assert client.put("/admin/economics", json={"margin_rate": -1}, headers=admin).status_code == 422
    assert client.put("/admin/economics", json={}, headers=admin).status_code == 422
    r = client.put("/admin/economics", json={"trip_cost": {"rural": 600}, "customer_multiplier": 5}, headers=admin).json()
    assert r["assumptions"]["trip_cost"]["rural"] == 600 and r["assumptions"]["trip_cost"]["garment_urban"] == 150 and r["assumptions"]["customer_multiplier"] == 5
    assert client.put("/admin/config", json={"coverage_prob": 0.9}, headers=admin).status_code == 200     # clears tier overrides
    ap = client.post("/admin/economics/apply-optimum", headers=admin).json()
    assert ap["applied"] == ap["optimum_params"]
    actions = [a["action"] for a in client.get("/admin/audit?limit=50", headers=admin).json()]
    assert "economics_update" in actions and "economics_apply_optimum" in actions
    assert client.post("/admin/economics/apply-optimum", headers=agent_a01).status_code == 403
    text = json.dumps(v)
    assert not any(k in text for k in ("true_cashout", "true_cashin", "unserved_cashout", "base_cashout", "noise_std"))
