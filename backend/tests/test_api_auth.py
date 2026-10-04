"""Auth + role isolation, enforced at the API level."""
from conftest import login

FORBIDDEN_KEYS = {"true_cashout_demand", "true_cashin_demand", "unserved_cashout", "unserved_cashin",
                  "base_cashout", "base_cashin", "noise_std"}


def _walk_keys(o):
    if isinstance(o, dict):
        for k, v in o.items():
            yield k
            yield from _walk_keys(v)
    elif isinstance(o, list):
        for v in o:
            yield from _walk_keys(v)


def test_login_and_me(client):
    h = login(client, "admin", "admin123")
    assert client.get("/me", headers=h).json()["role"] == "admin"
    h = login(client, "Agent A05", "agenta05")      # "Agent A05", "A05", "a05" are equivalent
    me = client.get("/me", headers=h).json()
    assert me["role"] == "agent" and me["agent_id"] == "A05"


def test_bad_login_uses_error_envelope(client):
    r = client.post("/auth/login", json={"username": "admin", "password": "nope"})
    assert r.status_code == 401
    assert set(r.json()["error"]) == {"code", "message", "details"}
    assert client.post("/auth/login", json={"username": "", "password": ""}).status_code == 422


def test_unauthenticated_requests_rejected(client):
    for path in ["/me", "/sim/state", "/agents/A01/forecast", "/admin/overview", "/alerts", "/impact"]:
        r = client.get(path)
        assert r.status_code == 401, path
        assert r.json()["error"]["code"] == "unauthorized"
    assert client.get("/me", headers={"Authorization": "Bearer garbage"}).status_code == 401


def test_agent_can_only_read_own_data(client, agent_a01):
    for path in ["/agents/A01", "/agents/A01/forecast", "/agents/A01/history"]:
        assert client.get(path, headers=agent_a01).status_code == 200, path
    for path in ["/agents/A02", "/agents/A02/forecast", "/agents/A02/history", "/agents/a02/forecast"]:
        r = client.get(path, headers=agent_a01)
        assert r.status_code == 403, path
        assert r.json()["error"]["code"] == "forbidden"
    assert client.post("/agents/A02/cash-report", json={"cash": 1000}, headers=agent_a01).status_code == 403


def test_agent_cannot_use_admin_endpoints(client, agent_a01):
    for method, path in [("get", "/agents"), ("get", "/admin/overview"), ("get", "/admin/dispatch-plan"), ("get", "/admin/config"),
                         ("get", "/admin/orders"), ("get", "/admin/events"), ("get", "/admin/audit"), ("get", "/agents/A01/reveal"),
                         ("post", "/sim/advance"), ("post", "/admin/orders"), ("put", "/admin/config"), ("post", "/admin/events")]:
        r = getattr(client, method)(path, headers=agent_a01, **({"json": {}} if method != "get" and path != "/sim/advance" else {}))
        assert r.status_code == 403, (method, path, r.status_code)


def test_admin_can_read_any_agent(client, admin):
    assert client.get("/agents/A07/forecast", headers=admin).status_code == 200
    assert len(client.get("/agents", headers=admin).json()) == 16


def test_alerts_are_scoped_to_the_agent(client, admin, agent_a01):
    client.post("/sim/advance", headers=admin)
    mine = client.get("/alerts", headers=agent_a01).json()
    assert all(a["agent_id"] == "A01" for a in mine)
    other = client.get("/alerts", headers=admin).json()
    foreign = next(a for a in other if a["agent_id"] != "A01")
    assert client.post(f"/alerts/{foreign['id']}/ack", headers=agent_a01).status_code == 404
    assert client.post(f"/alerts/{foreign['id']}/ack", headers=admin).json()["status"] == "acked"


def test_no_ground_truth_or_generator_internals_outside_reveal(client, admin, agent_a01):
    payloads = [client.get("/agents/A01/forecast", headers=agent_a01).json(), client.get("/agents/A01/history", headers=agent_a01).json(),
                client.get("/agents/A01", headers=agent_a01).json(), client.get("/admin/overview", headers=admin).json(),
                client.get("/admin/dispatch-plan", headers=admin).json(), client.get("/agents", headers=admin).json(),
                client.get("/alerts", headers=admin).json(), client.get("/impact", headers=admin).json(),
                client.get("/health").json()]
    for p in payloads:
        keys = set(_walk_keys(p))
        assert not (keys & FORBIDDEN_KEYS), keys & FORBIDDEN_KEYS
        assert not any(k.startswith("true_") for k in keys)
    rv = client.get("/agents/A01/reveal", headers=admin).json()
    assert "true_cashout" in rv["days"][0]            # only the admin reveal carries ground truth


def test_all_16_agents_log_in_with_agent_id_and_see_only_their_own_pages(client):
    for i in range(1, 17):
        aid = f"A{i:02d}"
        for who in (f"Agent {aid}", aid, aid.lower()):          # all spellings identify the same agent
            r = client.post("/auth/login", json={"username": who, "password": f"agent{aid.lower()}"})
            assert r.status_code == 200 and r.json()["user"]["agent_id"] == aid, who
        h = login(client, f"Agent {aid}", f"agent{aid.lower()}")
        assert client.get(f"/agents/{aid}/forecast?explain=false", headers=h).status_code == 200
        other = f"A{(i % 16) + 1:02d}"
        assert client.get(f"/agents/{other}/forecast", headers=h).status_code == 403
    bad = client.post("/auth/login", json={"username": "Agent A01", "password": "agent123"})
    assert bad.status_code == 401                                 # the old password no longer works
    assert client.post("/auth/login", json={"username": "Agent A01", "password": "agenta02"}).status_code == 401
