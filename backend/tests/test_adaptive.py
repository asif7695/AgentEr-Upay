"""Adaptive decision intelligence: rule gates and bounds, per-agent precedence, nightly proposals, approve / revert, no leakage."""
import copy
from datetime import date

import pytest

from app.rules import adaptive_rules as ar
from app.rules import business_rules as br
from app.services import adaptive
from app.services.context import ledger

BASE = dict(coverage_prob=0.70, buffer_frac=0.10, high_threshold=50.0, watch_threshold=30.0)
NET = dict(precision=0.20, alerts=100, vol_by_tier={"rural": 0.40}, vol_all=0.40)


def prof(**kw):
    p = dict(agent_id="A01", tier="rural", n_days=28, n_obs=56, breaches=6, vol=0.40, alert_n=10, alert_hits=2)
    p.update(kw)
    return p


def _clear():
    adaptive._profiles.clear(); adaptive._origins.clear(); adaptive._risks.clear()


def test_breach_z_nominal_is_zero():
    assert ar.breach_z(0.10, 100) == pytest.approx(0.0)
    assert ar.breach_z(0.20, 100) > 3 and ar.breach_z(0.0, 100) < -3 and ar.breach_z(0.5, 0) == 0.0


def test_no_change_without_evidence():
    out = ar.propose(prof(n_days=10, n_obs=10, breaches=5, alert_n=1, alert_hits=1), BASE, NET)
    assert out["values"] == {} and out["reasons"] == []
    assert ar.propose(prof(), BASE, NET)["values"] == {}          # a calibrated, typical agent is left alone


def test_coverage_up_is_significant_and_bounded():
    out = ar.propose(prof(breaches=40), BASE, NET)                 # 71% of flow-days above P90
    assert out["values"]["coverage_prob"] - BASE["coverage_prob"] <= ar.GUARD["cov_up"] + 1e-9
    assert out["values"]["coverage_prob"] > BASE["coverage_prob"] and out["reasons"][0]["code"] == "coverage_up"
    capped = ar.propose(prof(breaches=40), {**BASE, "coverage_prob": 0.98}, NET)
    assert capped["values"]["coverage_prob"] == ar.GUARD["cov_cap"]


def test_coverage_down_only_when_clearly_over_covered_and_floored():
    out = ar.propose(prof(breaches=0), BASE, NET)
    assert BASE["coverage_prob"] - out["values"]["coverage_prob"] <= ar.GUARD["cov_down"] + 1e-9
    assert "coverage_prob" not in ar.propose(prof(breaches=0), {**BASE, "coverage_prob": 0.50}, NET)["values"]       # at the floor: no change possible


def test_buffer_follows_relative_volatility_within_bounds():
    up = ar.propose(prof(vol=0.80), BASE, NET)["values"]["buffer_frac"]
    assert BASE["buffer_frac"] < up <= BASE["buffer_frac"] * ar.GUARD["buf_ratio"][1] + 1e-9
    down = ar.propose(prof(vol=0.10), BASE, NET)["values"]["buffer_frac"]
    assert ar.GUARD["buf_floor"] <= down < BASE["buffer_frac"]
    assert "buffer_frac" not in ar.propose(prof(vol=0.42), BASE, NET)["values"]       # inside the dead band


def test_thresholds_shift_with_shrunk_precision():
    early = ar.propose(prof(alert_n=30, alert_hits=18), BASE, NET)
    later = ar.propose(prof(alert_n=30, alert_hits=0), BASE, NET)
    assert early["values"]["high_threshold"] < BASE["high_threshold"] and later["values"]["high_threshold"] > BASE["high_threshold"]
    for o in (early, later):
        assert abs(o["values"]["high_threshold"] - BASE["high_threshold"]) <= ar.GUARD["thr_shift"] + 1e-9
        assert o["values"]["high_threshold"] - o["values"]["watch_threshold"] >= ar.GUARD["min_gap"] - 1e-9
    assert ar.propose(prof(alert_n=5, alert_hits=5), BASE, NET)["values"] == {}       # too few alerts to move anything
    mild = ar.propose(prof(alert_n=10, alert_hits=3), BASE, NET)["values"]             # shrinkage: 3 of 10 (30% vs 20% network) moves it only a little
    assert abs(mild.get("high_threshold", 50.0) - 50.0) < ar.GUARD["thr_shift"] / 2


def test_rule_validation_and_precedence():
    ok = br.validate_rules({"adaptive_mode": "auto", "agent_overrides": {"A01": {"coverage_prob": 0.8}}}, br.DEFAULT_RULES)
    assert ok["adaptive_mode"] == "auto"
    for bad in ({"adaptive_mode": "yolo"}, {"agent_overrides": {"A01": {"coverage_prob": 2}}}, {"agent_overrides": {"A01": {"nope": 1}}}, {"agent_overrides": []}):
        with pytest.raises(ValueError):
            br.validate_rules(bad, br.DEFAULT_RULES)
    r = {**br.DEFAULT_RULES, "agent_overrides": {"A01": {"coverage_prob": 0.9, "high_threshold": 40.0, "watch_threshold": 20.0}}}
    assert br.risk_cfg_overrides(r, "rural", "A01")["coverage_prob"] == 0.9                       # agent > tier
    assert br.risk_cfg_overrides(r, "rural", "A02")["coverage_prob"] == r["coverage_by_tier"]["rural"]
    assert br.thresholds(r, "A01") == (40.0, 20.0) and br.thresholds(r, "A02") == (50.0, 30.0)
    assert br.config_hash(r, "rural", "A01") != br.config_hash(r, "rural", "A02")                 # the cache splits per adapted agent


def test_api_is_admin_only_and_has_no_ground_truth(client, admin, agent_a01):
    assert client.get("/admin/adaptive", headers=agent_a01).status_code == 403
    r = client.get("/admin/adaptive", headers=admin)
    assert r.status_code == 200
    for k in ("true_cashout", "true_cashin", "unserved_cash", "base_cashout", "noise_std"):
        assert k not in r.text
    j = r.json()
    assert j["mode"] == "suggest" and len(j["agents"]) == 16 and j["date"] == "2025-09-01"


def test_profile_uses_only_data_up_to_the_date(client):
    from app.db import SessionLocal
    from app.services.context import Ctx
    with SessionLocal() as db:
        ctx = Ctx(db)
        d = date(2025, 9, 1)
        _clear()
        before = adaptive.agent_profile(ctx, "A01", d)
        orig = ledger.frames
        try:
            frames = copy.deepcopy(orig)
            g = frames["A01"]
            fut = g["date"] > "2025-09-01"
            g.loc[fut, ["observed_cashout", "observed_cashin"]] *= 7
            g.loc[fut, ["cash_stockout", "efloat_stockout"]] = 1
            ledger.frames = frames
            _clear()
            after = adaptive.agent_profile(ctx, "A01", d)
        finally:
            ledger.frames = orig
            _clear()
    assert before == after


def _first_proposal(client, admin):
    client.post("/sim/jump", json={"date": "2025-10-15"}, headers=admin)
    j = client.get("/admin/adaptive", headers=admin).json()
    props = [c for c in j["changes"] if c["status"] == "proposed"]
    assert props, "expected proposals after the nightly run"
    return props[0]


def test_suggest_mode_proposes_without_changing_anything_then_approve_and_revert(client, admin):
    p = _first_proposal(client, admin)
    assert client.get("/admin/config", headers=admin).json()["rules"]["agent_overrides"] == {}        # nothing applied yet
    aid = p["agent_id"]
    base_fc = client.get(f"/agents/{aid}/forecast?explain=false", headers=admin).json()
    r = client.post(f"/admin/adaptive/changes/{p['id']}/approve", headers=admin)
    assert r.status_code == 200 and r.json()["status"] == "applied"
    ov = client.get("/admin/config", headers=admin).json()["rules"]["agent_overrides"][aid]
    fc = client.get(f"/agents/{aid}/forecast?explain=false", headers=admin).json()
    assert fc["adaptive"]["overrides"] == ov
    if "high_threshold" in ov:
        assert fc["thresholds"]["high"] == ov["high_threshold"] and fc["thresholds"]["adapted"] is True
    if "coverage_prob" in ov:
        assert fc["config"]["coverage_prob"] == ov["coverage_prob"] != base_fc["config"]["coverage_prob"]
    assert client.post(f"/admin/adaptive/changes/{p['id']}/approve", headers=admin).status_code == 409     # not twice
    r = client.post(f"/admin/adaptive/changes/{p['id']}/revert", headers=admin)
    assert r.json()["status"] == "reverted"
    assert aid not in client.get("/admin/config", headers=admin).json()["rules"]["agent_overrides"]
    acts = [a["action"] for a in client.get("/admin/audit?limit=100", headers=admin).json()]
    assert {"adaptive_propose", "adaptive_apply", "adaptive_revert"} <= set(acts)


def test_dismiss_and_unknown_change(client, admin, agent_a01):
    p = _first_proposal(client, admin)
    assert client.post(f"/admin/adaptive/changes/{p['id']}/dismiss", headers=agent_a01).status_code == 403
    assert client.post(f"/admin/adaptive/changes/{p['id']}/dismiss", headers=admin).json()["status"] == "dismissed"
    assert client.post(f"/admin/adaptive/changes/{p['id']}/approve", headers=admin).status_code == 409
    assert client.post("/admin/adaptive/changes/99999/approve", headers=admin).status_code == 404


def test_off_mode_does_nothing_and_auto_mode_applies_within_bounds(client, admin):
    client.put("/admin/config", json={"adaptive_mode": "off"}, headers=admin)
    client.post("/sim/jump", json={"date": "2025-10-15"}, headers=admin)
    assert client.get("/admin/adaptive", headers=admin).json()["changes"] == []
    client.put("/admin/config", json={"adaptive_mode": "auto"}, headers=admin)
    client.post("/sim/jump", json={"date": "2025-10-16"}, headers=admin)
    j = client.get("/admin/adaptive", headers=admin).json()
    applied = [c for c in j["changes"] if c["status"] == "applied"]
    assert applied and all(c["decided_by"] == "system" and c["mode"] == "auto" for c in applied)
    ov = client.get("/admin/config", headers=admin).json()["rules"]["agent_overrides"]
    g = ar.GUARD
    for vals in ov.values():
        assert g["cov_floor"] <= vals.get("coverage_prob", 0.7) <= g["cov_cap"]
        assert g["buf_floor"] <= vals.get("buffer_frac", 0.1) <= g["buf_cap"]
        if "high_threshold" in vals:
            assert vals["high_threshold"] - vals["watch_threshold"] >= g["min_gap"] - 1e-9
