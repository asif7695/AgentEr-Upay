"""Unusual-event detection: maths, censoring, proposals, accept / dismiss / revoke, auto-mode limits, no leakage."""
from datetime import date, timedelta

import numpy as np
import pandas as pd
import pytest

from app.ml import anomaly
from app.services import adaptive, anomalies
from app.services.context import Ctx, ledger

Q = np.array([80.0, 90.0, 100.0, 110.0, 120.0])        # a forecast: median 100, P10-P90 = 80-120


def series(vals, n=20):
    y = [100.0] * (n - len(vals)) + list(vals)
    return y, [Q] * n, [False] * n


def test_pit_and_z_are_monotone_and_centred():
    assert anomaly.zscore(100, Q) == pytest.approx(0.0, abs=1e-6)
    zs = [anomaly.zscore(v, Q) for v in (40, 80, 100, 120, 200)]
    assert zs == sorted(zs) and zs[0] < -1.5 and zs[-1] > 1.5


def test_cusum_flags_a_sustained_shift_only():
    flat = anomaly.cusum([0.1, -0.2, 0.3, -0.1, 0.0, 0.2] * 3)
    assert not flat["alarm_up"] and not flat["alarm_down"]
    up = anomaly.cusum([0.0] * 6 + [1.8] * 5)
    assert up["alarm_up"] and up["run_up"] >= 5 and not up["alarm_down"]


def test_quiet_series_is_not_flagged_and_single_extreme_day_is_not_enough():
    y, q, c = series([])
    assert anomaly.detect_flow(y, q, c) is None
    y, q, c = series([100, 100, 100, 100, 100, 100, 190])        # one huge day: ordinary fat-tail noise
    assert anomaly.detect_flow(y, q, c) is None


def test_two_day_jump_up_and_down_with_bounded_multiplier():
    y, q, c = series([100, 100, 100, 100, 100, 100, 190, 200])
    d = anomaly.detect_flow(y, q, c)
    assert d and d["direction"] == "up" and d["kind"] in ("jump", "shift")
    assert 1.0 < d["multiplier"] <= anomaly.MULT_BOUNDS[1]
    assert d["multiplier"] < d["raw_ratio"]                       # shrunk: the model's own lags partly adapt
    y, q, c = series([100] * 6 + [40, 35])
    d = anomaly.detect_flow(y, q, c)
    assert d and d["direction"] == "down" and anomaly.MULT_BOUNDS[0] <= d["multiplier"] < 1.0


def test_censored_days_only_confirm_upward_moves():
    y, q, c = series([100] * 6 + [40, 35])
    c[-2:] = [True, True]                                          # the agent ran out: low sales say nothing about demand
    assert anomaly.detect_flow(y, q, c) is None
    y, q, c = series([100] * 6 + [190, 200])
    c[-2:] = [True, True]
    d = anomaly.detect_flow(y, q, c)
    assert d and d["direction"] == "up"


def test_sustained_shift_is_found_by_cusum():
    y, q, c = series([100] * 5 + [150, 148, 152, 149, 151])
    d = anomaly.detect_flow(y, q, c)
    assert d and d["direction"] == "up" and d["days"] >= 3


@pytest.fixture()
def shocked(client):
    """A copy of the ledger with A03's cash-out doubled for 10-14 Oct; restored afterwards."""
    orig = ledger.frames
    frames = {a: f.copy() for a, f in orig.items()}
    g = frames["A03"]
    win = (g["date"] >= "2025-10-10") & (g["date"] <= "2025-10-14")
    g.loc[win, "observed_cashout"] = g.loc[win, "observed_cashout"] * 2.0
    ledger.frames = frames
    adaptive.invalidate()
    yield
    ledger.frames = orig
    adaptive.invalidate()


def _ctx():
    from app.db import SessionLocal
    return SessionLocal()


def test_detects_injected_shock_and_proposal_lifecycle(shocked):
    with _ctx() as db:
        ctx = Ctx(db)
        found = None
        for k in range(1, 5):
            d = date(2025, 10, 10) + timedelta(days=k)
            r = anomalies.run_nightly(ctx, d)
            db.commit()
            if r["proposed"]:
                found = d
                break
        assert found is not None, "the doubled cash-out was never noticed"
        rows = anomalies.listing(ctx)
        p = next(x for x in rows if x["target"] == "A03")
        assert p["status"] == "proposed" and p["direction"] == "up" and 1.0 < p["multiplier"] <= 2.5
        assert p["start_date"] == (found + timedelta(days=1)).isoformat() and p["end_date"] == (found + timedelta(days=7)).isoformat()
        assert not [e for e in ctx.events if e["kind"] == "detected"]          # nothing live until a person accepts
        # a repeat run the next night does not duplicate the proposal while the window overlaps
        anomalies.run_nightly(ctx, found + timedelta(days=1))
        db.commit()
        assert len([x for x in anomalies.listing(ctx) if x["target"] == "A03" and x["status"] == "proposed"]) == 1
        ctx.sim_date = found
        out = anomalies.decide(ctx, "admin", p["id"], "accept")
        assert out["status"] == "accepted" and out["event_id"]
        ctx2 = Ctx(db)
        assert any(e["kind"] == "detected" and e["multiplier"] == p["multiplier"] for e in ctx2.events)
        assert anomalies.decide(ctx2, "admin", p["id"], "revoke")["status"] == "revoked"
        assert not [e for e in Ctx(db).events if e["kind"] == "detected"]
        with pytest.raises(Exception):
            anomalies.decide(ctx2, "admin", p["id"], "accept")                 # already decided


def test_auto_mode_accepts_small_but_not_large_adjustments(shocked):
    with _ctx() as db:
        ctx = Ctx(db)
        ctx.rules["adaptive_mode"] = "auto"
        for k in range(1, 5):
            anomalies.run_nightly(ctx, date(2025, 10, 10) + timedelta(days=k))
            db.commit()
        row = next((x for x in anomalies.listing(ctx) if x["target"] == "A03"), None)
        assert row is not None
        small = 1 / anomalies.AUTO_MAX_MULT <= row["multiplier"] <= anomalies.AUTO_MAX_MULT
        assert row["status"] == ("accepted" if small else "proposed")
        if small:
            assert row["decided_by"] == "system"


def test_api_admin_only_clear_errors_and_no_ground_truth(client, admin, agent_a01):
    assert client.get("/admin/detected-events", headers=agent_a01).status_code == 403
    r = client.get("/admin/detected-events", headers=admin)
    assert r.status_code == 200 and r.json() == []
    assert client.post("/admin/detected-events/1/accept", headers=agent_a01).status_code == 403
    assert client.post("/admin/detected-events/999/accept", headers=admin).status_code == 404
    assert client.post("/admin/detected-events/1/explode", headers=admin).status_code == 422
    for k in ("true_cashout", "unserved_cash", "base_cashout", "noise_std"):
        assert k not in r.text


def test_detection_uses_only_data_up_to_the_night(client):
    with _ctx() as db:
        ctx = Ctx(db)
        d = date(2025, 10, 12)
        adaptive.invalidate()
        before = anomalies.detect_agent(ctx, "A03", d)
        orig = ledger.frames
        try:
            frames = {a: f.copy() for a, f in orig.items()}
            g = frames["A03"]
            g.loc[g["date"] > pd.Timestamp(d), ["observed_cashout", "observed_cashin"]] *= 9
            ledger.frames = frames
            adaptive.invalidate()
            after = anomalies.detect_agent(ctx, "A03", d)
        finally:
            ledger.frames = orig
            adaptive.invalidate()
    assert before == after
