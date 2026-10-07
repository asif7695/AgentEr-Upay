"""Distributor routes: distance, capacity, day length, priority, determinism of the synthetic geography, and the API."""
import math

import pytest

from app.rules import routing as rt
from app.services import geo

S = {**rt.DEFAULT_ROUTING, "day_hours": 24.0, "vehicle_cash_limit": 10_000_000.0}
DEPOT = (23.8103, 90.4125)


def stop(key, dlat, dlon, kind="cash", amount=50_000.0, w=1.0):
    return rt.Stop(key, key.split(":")[0], kind, DEPOT[0] + dlat, DEPOT[1] + dlon, amount, w)


def test_haversine_known_distance_and_symmetry():
    dhaka, ctg = geo.depot("Dhaka"), geo.depot("Chattogram")
    assert 200 < rt.dist_km(dhaka, ctg) < 230
    assert rt.dist_km(dhaka, ctg) == pytest.approx(rt.dist_km(ctg, dhaka)) and rt.dist_km(dhaka, dhaka) == 0.0


def test_evaluate_round_trip_and_empty_route():
    a = stop("A01:cash", 0.1, 0.0)
    ev = rt.evaluate([a], DEPOT, S)
    assert ev["distance_km"] == pytest.approx(2 * rt.dist_km(DEPOT, a.pos))
    assert ev["duration_min"] == pytest.approx(ev["distance_km"] / S["speed_kmh"] * 60 + S["service_minutes"])
    assert rt.evaluate([], DEPOT, S)["distance_km"] == 0.0


def test_every_stop_visited_once_and_never_longer_than_id_order():
    stops = [stop(f"A{i:02d}:cash", 0.2 * math.sin(i * 1.7), 0.2 * math.cos(i * 2.3)) for i in range(1, 13)]
    res = rt.plan_division(DEPOT, stops, S)
    keys = [x["key"] for r in res["routes"] for x in r["stops"]]
    assert sorted(keys) == sorted(s.key for s in stops) and not res["unrouted"]
    assert res["distance_km"] <= res["naive_km"] + 1e-9 and res["saving_km"] >= 0


def test_urgent_stop_is_served_first_when_distance_is_a_tie():
    low = stop("A01:cash", 0.25, 0.0, w=1.0)            # opposite directions, same distance: the tour length is identical either way
    high = stop("A02:cash", -0.25, 0.0, w=3.0)
    order = rt.plan_division(DEPOT, [low, high], S)["routes"][0]["stops"]
    assert order[0]["key"] == "A02:cash"


def test_a_stop_on_the_way_is_not_sacrificed_to_priority():
    near_low = stop("A01:cash", 0.02, 0.0, w=1.0)       # 2 km out, the urgent stop is 33 km the other way: visiting the near one first costs almost nothing
    far_high = stop("A02:cash", -0.30, 0.0, w=3.0)
    order = rt.plan_division(DEPOT, [near_low, far_high], S)["routes"][0]["stops"]
    assert [x["key"] for x in order] == ["A01:cash", "A02:cash"]


def test_cash_limit_splits_vehicles_then_reports_what_cannot_be_carried():
    stops = [stop(f"A{i:02d}:cash", 0.05 * i, 0.03 * i, amount=60_000.0) for i in range(1, 5)]
    s = {**S, "vehicle_cash_limit": 130_000.0, "vehicles_per_division": 2}
    res = rt.plan_division(DEPOT, stops, s)
    assert len(res["routes"]) == 2 and all(r["cash_out"] <= 130_000.0 for r in res["routes"]) and not res["unrouted"]
    one = rt.plan_division(DEPOT, stops, {**s, "vehicles_per_division": 1})
    assert {u["reason"] for u in one["unrouted"]} == {"no_vehicle"} and len(one["unrouted"]) == 2
    big = rt.plan_division(DEPOT, [stop("A01:cash", 0.1, 0.1, amount=500_000.0)], s)
    assert big["unrouted"][0]["reason"] == "over_capacity" and not big["routes"]


def test_efloat_orders_bring_cash_back_and_do_not_count_against_the_limit():
    s = {**S, "vehicle_cash_limit": 50_000.0}
    res = rt.plan_division(DEPOT, [stop("A01:cash", 0.1, 0.0, amount=50_000.0), stop("A02:efloat", -0.1, 0.0, "efloat", 90_000.0)], s)
    r = res["routes"][0]
    assert not res["unrouted"] and r["cash_out"] == 50_000.0 and r["cash_in"] == 90_000.0


def test_short_day_drops_the_lowest_priority_stops_and_says_so():
    stops = [stop("A01:cash", 0.4, 0.0, w=3.0), stop("A02:cash", -0.4, 0.0, w=1.0), stop("A03:cash", 0.0, 0.4, w=1.0)]
    res = rt.plan_division(DEPOT, stops, {**S, "day_hours": 4.0})
    kept = {x["key"] for r in res["routes"] for x in r["stops"]}
    assert res["unrouted"] and all(u["reason"] == "no_time" for u in res["unrouted"])
    assert "A01:cash" in kept and all(r["duration_min"] <= 4.0 * 60 + 1e-6 for r in res["routes"])


def test_validate_routing():
    ok = rt.validate_routing({"vehicles_per_division": 3}, rt.DEFAULT_ROUTING)
    assert ok["vehicles_per_division"] == 3 and isinstance(ok["speed_kmh"], float)
    for bad in ({"vehicles_per_division": 0}, {"speed_kmh": 0}, {"day_hours": 99}, {"vehicle_cash_limit": float("nan")}, {"speed_kmh": "fast"}):
        with pytest.raises(ValueError):
            rt.validate_routing(bad, rt.DEFAULT_ROUTING)


def test_synthetic_geography_is_deterministic_and_respects_tiers():
    a1, a2 = geo.agent_position("A01", "Dhaka", "rural"), geo.agent_position("A01", "Dhaka", "rural")
    assert a1 == a2
    rural = rt.dist_km(geo.depot("Dhaka"), geo.agent_position("A02", "Dhaka", "rural"))
    urban = rt.dist_km(geo.depot("Dhaka"), geo.agent_position("A02", "Dhaka", "garment_urban"))
    assert 14 < rural < 46 and 2.5 < urban < 15


def test_api_routes_are_admin_only_and_match_the_plan(client, admin, agent_a01):
    assert client.get("/admin/routes", headers=agent_a01).status_code == 403
    r = client.get("/admin/routes", headers=admin)
    assert r.status_code == 200
    j = r.json()
    assert j["synthetic_geography"] is True and "SYNTHETIC" in j["note"]
    for k in ("true_cashout", "unserved_cash", "base_cashout", "noise_std"):
        assert k not in r.text
    plan = client.get("/admin/allocation", headers=admin).json()
    wanted = {ln["key"]: ln["amount"] for ln in plan["lines"] if ln["amount"] > 0}
    routed = {s["key"]: s["amount"] for d in j["divisions"] for rt_ in d["routes"] for s in rt_["stops"]}
    unrouted = {u["key"] for d in j["divisions"] for u in d["unrouted"]}
    assert set(routed) | unrouted == set(wanted) and all(routed[k] == wanted[k] for k in routed)
    assert j["totals"]["stops"] == len(routed) and j["totals"]["saving_km"] >= 0


def test_routing_settings_validation_audit_and_effect(client, admin):
    assert client.put("/admin/routes/settings", json={"speed_kmh": 0}, headers=admin).status_code == 422
    assert client.put("/admin/routes/settings", json={}, headers=admin).status_code == 422
    r = client.put("/admin/routes/settings", json={"vehicle_cash_limit": 10_000}, headers=admin)
    assert r.status_code == 200 and r.json()["settings"]["vehicle_cash_limit"] == 10_000
    assert r.json()["totals"]["unrouted"] > 0                              # nothing fits a 10,000 BDT cash limit
    assert "routing_settings" in [a["action"] for a in client.get("/admin/audit?limit=20", headers=admin).json()]
