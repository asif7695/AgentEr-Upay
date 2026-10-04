"""Sim clock, cash-report loop, rules/events, dispatch + orders, audit log."""
from conftest import login


def test_sim_state_and_advance(client, admin, agent_a01):
    s = client.get("/sim/state", headers=agent_a01).json()
    assert s["date"] == "2025-09-01" and s["can_advance"] and s["min_date"] == "2025-01-28"
    r = client.post("/sim/advance", headers=admin).json()
    assert r["state"]["date"] == "2025-09-02"
    pl = r["pipeline"]
    assert pl["ledger_rows_ingested"] == 16 and pl["forecasts_recomputed"] == 16
    assert client.get("/sim/state", headers=agent_a01).json()["date"] == "2025-09-02"
    assert client.post("/sim/advance", headers=agent_a01).status_code == 403


def test_jump_bounds_and_end_of_data(client, admin):
    assert client.post("/sim/jump", json={"date": "2025-01-27"}, headers=admin).status_code == 422
    assert client.post("/sim/jump", json={"date": "2026-01-01"}, headers=admin).status_code == 422
    assert client.post("/sim/jump", json={"date": "nonsense"}, headers=admin).status_code == 422
    assert client.post("/sim/jump", json={"date": "2025-12-31"}, headers=admin).status_code == 200
    r = client.post("/sim/advance", headers=admin)
    assert r.status_code == 409 and r.json()["error"]["code"] == "end_of_data"


def test_reveal_window(client, admin):
    assert client.get("/agents/A01/reveal", headers=admin).status_code == 200
    client.post("/sim/jump", json={"date": "2025-12-25"}, headers=admin)
    r = client.get("/agents/A01/reveal", headers=admin)
    assert r.status_code == 409 and r.json()["error"]["code"] == "reveal_unavailable"
    client.post("/sim/jump", json={"date": "2025-12-24"}, headers=admin)
    assert client.get("/agents/A01/reveal", headers=admin).status_code == 200


def test_alerts_created_on_advance_and_ack(client, admin):
    client.post("/sim/advance", headers=admin)
    alerts = client.get("/alerts?status=open", headers=admin).json()
    assert alerts and all({"id", "agent_id", "type", "severity", "message"} <= set(a) for a in alerts)
    a = alerts[0]
    assert client.post(f"/alerts/{a['id']}/ack", headers=admin).json()["status"] == "acked"
    assert a["id"] not in [x["id"] for x in client.get("/alerts?status=open", headers=admin).json()]


def test_cash_report_updates_reconciliation_instantly(client, admin):
    client.put("/admin/config", json={"manual_report_agents": ["A02"]}, headers=admin)
    h = login(client, "a02", "agenta02")
    f0 = client.get("/agents/A02/forecast?explain=false", headers=h).json()
    assert f0["reconciliation"]["status"] == "pending" and f0["reconciliation"]["label"] == "Estimated, not confirmed today"
    ledger_cash = f0["reconciliation"]["ledger_cash"]
    # within tolerance -> reported value is used for the forecast
    r = client.post("/agents/A02/cash-report", json={"cash": round(ledger_cash * 0.95)}, headers=h)
    assert r.status_code == 200
    rec = r.json()["reconciliation"]
    assert rec["status"] == "confirmed" and rec["cash_source"] == "reported"
    assert r.json()["forecast"]["balances"]["cash"]["value"] == round(ledger_cash * 0.95)
    # > 10% gap -> flagged, ledger value used, neutral wording
    r = client.post("/agents/A02/cash-report", json={"cash": round(ledger_cash * 1.4)}, headers=h).json()
    assert r["reconciliation"]["status"] == "needs_verification" and r["forecast"]["balances"]["cash"]["value"] == round(ledger_cash)
    assert "verification" in r["message"] and "fraud" not in r["message"].lower()
    assert any(a["type"] == "report_gap" for a in client.get("/alerts", headers=h).json())


def test_cash_report_validation(client, agent_a01):
    for bad in ({"cash": -1}, {"cash": "abc"}, {"cash": None}, {}, {"cash": 1e12}, {"cash": 100, "date": "2025-09-05"}):
        r = client.post("/agents/A01/cash-report", json=bad, headers=agent_a01)
        assert r.status_code == 422, bad
        assert r.json()["error"]["code"] == "validation_error"
    assert client.post("/agents/A01/cash-report", json={"cash": 0}, headers=agent_a01).status_code == 200


def test_missing_report_uses_ledger_estimate(client, admin):
    # find any agent-date with a missing replay report and check the forecast labels it
    import sqlite3
    from app import settings
    con = sqlite3.connect(settings.DB_URL.replace("sqlite:///", ""))
    aid, d = con.execute("select agent_id, date from reports where status='missing' and agent_id != 'A01' and date between '2025-02-01' and '2025-12-31' limit 1").fetchone()
    client.post("/sim/jump", json={"date": d}, headers=admin)
    f = client.get(f"/agents/{aid}/forecast?explain=false", headers=admin).json()
    assert f["reconciliation"]["status"] == "missing" and f["balances"]["cash"]["source"] == "ledger_estimate"
    assert any(a["type"] == "report_missing" for a in client.get(f"/alerts?agent_id={aid}", headers=admin).json())


def test_rules_change_reruns_forecast_and_is_audited(client, admin):
    base = client.get("/agents/A15/forecast?explain=false", headers=admin).json()
    r = client.put("/admin/config", json={"coverage_prob": 0.80, "buffer_frac": 0.2}, headers=admin)
    assert r.status_code == 200 and r.json()["rules"]["coverage_prob"] == 0.8
    new = client.get("/agents/A15/forecast?explain=false", headers=admin).json()
    assert new["config"]["buffer_frac"] == 0.2 and new["cash"]["buffer"] != base["cash"]["buffer"]
    assert new["cash"]["recommended_level"] != base["cash"]["recommended_level"]
    log = client.get("/admin/audit", headers=admin).json()
    assert any(x["action"] == "config_update" and "coverage_prob" in x["detail"] for x in log)
    for bad in ({"coverage_prob": 2}, {"watch_threshold": 80}, {"buffer_frac": "x"}):
        assert client.put("/admin/config", json=bad, headers=admin).status_code == 422
    assert client.put("/admin/config", json={}, headers=admin).status_code == 422


def test_threshold_change_changes_status_without_resimulation(client, admin):
    ov = client.get("/admin/overview", headers=admin).json()
    r = client.put("/admin/config", json={"high_threshold": 99, "watch_threshold": 98}, headers=admin)
    assert r.status_code == 200
    ov2 = client.get("/admin/overview", headers=admin).json()
    assert ov2["kpis"]["high"] < ov["kpis"]["high"]


def test_event_override_is_labelled_and_changes_forecast(client, admin):
    base = client.get("/agents/A01/forecast?explain=false", headers=admin).json()
    ev = client.post("/admin/events", json={"scope": "division", "target": "Dhaka", "kind": "fair", "multiplier": 1.8, "flow": "cashout",
                                            "start_date": "2025-09-02", "end_date": "2025-09-06", "note": "Boi mela"}, headers=admin)
    assert ev.status_code == 201 and ev.json()["label"] == "manual adjustment, not learned by the model"
    new = client.get("/agents/A01/forecast?explain=false", headers=admin).json()
    assert new["events"] and new["events"][0]["label"] == "manual adjustment, not learned by the model"
    assert new["days"][0]["cashout"]["p50"] > base["days"][0]["cashout"]["p50"]
    assert new["days"][0]["cashin"]["p50"] == base["days"][0]["cashin"]["p50"]
    other = client.get("/agents/A03/forecast?explain=false", headers=admin).json()           # Chattogram: unaffected
    assert other["events"] == []
    assert client.delete(f"/admin/events/{ev.json()['id']}", headers=admin).json()["active"] is False
    again = client.get("/agents/A01/forecast?explain=false", headers=admin).json()
    assert again["days"][0]["cashout"]["p50"] == base["days"][0]["cashout"]["p50"]


def test_event_validation(client, admin):
    ok = {"scope": "all", "kind": "flood", "multiplier": 0.5, "start_date": "2025-09-02", "end_date": "2025-09-03"}
    assert client.post("/admin/events", json=ok, headers=admin).status_code == 201
    for patch in ({"multiplier": 0}, {"multiplier": 50}, {"end_date": "2025-09-01"}, {"scope": "agent", "target": "Z99"},
                  {"scope": "division", "target": "Atlantis"}, {"kind": "party"}):
        assert client.post("/admin/events", json={**ok, **patch}, headers=admin).status_code == 422, patch


def test_dispatch_plan_and_order_lifecycle(client, admin):
    plan = client.get("/admin/dispatch-plan", headers=admin).json()
    items = [i for d in plan["divisions"] for i in d["items"]]
    assert items, "the default replay date should have at least one recommended top-up"
    for d in plan["divisions"]:
        assert d["total_cash"] == sum(i["amount"] for i in d["items"] if i["kind"] == "cash")
    it = items[0]
    body = {"agent_id": it["agent_id"], "kind": it["kind"], "amount": it["amount"], "due_date": it["by_date"], "order_type": it["order_type"]}
    o = client.post("/admin/orders", json=body, headers=admin)
    assert o.status_code == 201 and o.json()["status"] == "acknowledged"
    assert client.post("/admin/orders", json=body, headers=admin).status_code == 409           # no duplicate for the same plan
    oid = o.json()["id"]
    assert client.patch(f"/admin/orders/{oid}", json={"status": "scheduled", "scheduled_for": it["by_date"]}, headers=admin).json()["status"] == "scheduled"
    assert client.patch(f"/admin/orders/{oid}", json={"status": "acknowledged"}, headers=admin).status_code == 409
    assert client.patch(f"/admin/orders/{oid}", json={"status": "done"}, headers=admin).json()["status"] == "done"
    assert client.patch(f"/admin/orders/{oid}", json={"status": "cancelled"}, headers=admin).status_code == 409
    plan2 = client.get("/admin/dispatch-plan", headers=admin).json()
    assert plan2["totals"]["orders"] == 1
    assert any(a["action"].startswith("order_") for a in client.get("/admin/audit", headers=admin).json())


def test_order_validation(client, admin):
    ok = {"agent_id": "A01", "kind": "cash", "amount": 1000, "due_date": "2025-09-03"}
    for patch in ({"amount": 0}, {"amount": -5}, {"kind": "gold"}, {"agent_id": "A99"}, {"due_date": "2025-08-01"}, {"order_type": "rush"}):
        assert client.post("/admin/orders", json={**ok, **patch}, headers=admin).status_code in (404, 422), patch
    assert client.patch("/admin/orders/9999", json={"status": "done"}, headers=admin).status_code == 404


def test_history_endpoint(client, agent_a01):
    h = client.get("/agents/A01/history?days=30", headers=agent_a01).json()
    assert len(h["rows"]) == 30 and h["rows"][-1]["date"] == "2025-09-01"
    assert client.get("/agents/A01/history?days=0", headers=agent_a01).status_code == 422


def test_impact_static(client, agent_a01):
    i = client.get("/impact", headers=agent_a01).json()
    pol = {p["key"]: p for p in i["policy_replay"]["policies"]}
    assert pol["habit"]["stockout_days"] == 64 and pol["hybrid"]["stockout_days"] == 29 and pol["model_only"]["stockout_days"] == 76
    assert i["policy_replay"]["deltas"]["hybrid_vs_habit"]["orders_pct"] == 62.8
    assert i["label"] == "Simulation on synthetic data"
