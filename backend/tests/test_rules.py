"""Pure business-rule tests: reconciliation edge cases, status bands, top-up timing, event multipliers."""
from datetime import date

import numpy as np
import pytest

from app.rules import business_rules as br


def test_reconcile_within_tolerance_uses_reported():
    r = br.reconcile(100_000, 95_000)
    assert r["status"] == "confirmed" and r["cash_used"] == 95_000 and r["cash_source"] == "reported"
    assert r["gap"] == -5_000 and r["gap_pct"] == pytest.approx(-0.05)


def test_reconcile_gap_over_10pct_flags_and_uses_ledger():
    for rep in (115_000, 85_000):
        r = br.reconcile(100_000, rep)
        assert r["status"] == "needs_verification" and r["flagged"] is True
        assert r["cash_used"] == 100_000 and r["cash_source"] == "ledger_estimate"
        assert r["label"] == "Needs verification"      # neutral wording, no accusation


def test_reconcile_exactly_10pct_is_not_flagged():
    assert br.reconcile(100_000, 110_000)["status"] == "confirmed"
    assert br.reconcile(100_000, 90_000)["status"] == "confirmed"
    assert br.reconcile(100_000, 110_001)["status"] == "needs_verification"


def test_reconcile_missing_report_uses_ledger_estimate():
    r = br.reconcile(80_000, None)
    assert r["status"] == "missing" and r["cash_used"] == 80_000 and r["gap_pct"] is None
    assert r["label"] == "Estimated, not confirmed today"
    assert br.reconcile(80_000, float("nan"))["status"] == "missing"
    assert br.reconcile(80_000, None, pending=True)["status"] == "pending"


def test_reconcile_zero_ledger_cash():
    assert br.reconcile(0, 0)["status"] == "confirmed"
    r = br.reconcile(0, 5_000)
    assert r["status"] == "needs_verification" and r["gap_pct"] is None and r["cash_used"] == 0


def test_status_bands():
    assert br.status_from_risk(50, 50, 30) == "HIGH"
    assert br.status_from_risk(49.9, 50, 30) == "WATCH"
    assert br.status_from_risk(30, 50, 30) == "WATCH"
    assert br.status_from_risk(29.9, 50, 30) == "OK"
    assert br.worst_status("OK", "HIGH", "WATCH") == "HIGH"


def test_rule_validation():
    cur = dict(br.DEFAULT_RULES)
    assert br.validate_rules({"coverage_prob": 0.9}, cur)["coverage_prob"] == 0.9
    for bad in ({"buffer_frac": 0.9}, {"coverage_prob": 0.1}, {"watch_threshold": 60}, {"high_threshold": float("nan")},
                {"manual_report_agents": "A01"}):
        with pytest.raises(ValueError):
            br.validate_rules(bad, cur)


def test_config_hash_changes_only_with_forecast_relevant_rules():
    base = dict(br.DEFAULT_RULES)
    assert br.config_hash(base) == br.config_hash({**base, "high_threshold": 60.0})       # thresholds don't re-simulate
    assert br.config_hash(base) != br.config_hash({**base, "coverage_prob": 0.9})


def test_topup_by_date_respects_working_days():
    # origin Wed 3 Sep 2025; Fri/Sat are closed
    work = {date(2025, 9, 3 + k): (date(2025, 9, 3 + k).weekday() not in (4, 5)) for k in range(0, 22)}
    o = date(2025, 9, 3)
    assert br.next_working_day(o, work) == date(2025, 9, 4)                   # Thursday
    assert br.next_working_day(date(2025, 9, 4), work) == date(2025, 9, 7)    # Fri+Sat closed -> Sunday
    r = br.topup_by_date(o, 5, work)                                          # run-out Mon 8 Sep: last working day before it = Sun 7
    assert r["by_date"] == date(2025, 9, 7) and not r["late"]
    r = br.topup_by_date(o, 1, work)                                          # run-out tomorrow: nothing earlier is possible
    assert r["by_date"] == date(2025, 9, 4) and r["late"]
    assert br.topup_by_date(o, None, work)["by_date"] == date(2025, 9, 4)


def test_capital_gap_and_order_type():
    assert br.capital_gap(120_000, 40_000, 100_000, 30_000) == 30_000
    assert br.capital_gap(10, 10, 100, 100) == 0
    assert br.order_type("HIGH", {"late": True}) == "emergency"
    assert br.order_type("WATCH", {"late": True}) == "planned"
    assert br.order_type("HIGH", {"late": False}) == "planned"


def test_event_multipliers_scope_dates_and_flow():
    agent = {"agent_id": "A01", "division": "Dhaka"}
    days = [date(2025, 9, 2 + k) for k in range(7)]
    ev = [dict(scope="division", target="Dhaka", flow="cashout", multiplier=1.5, start_date="2025-09-03", end_date="2025-09-04", active=True),
          dict(scope="agent", target="A02", flow="both", multiplier=9.0, start_date="2025-09-01", end_date="2025-09-30", active=True),
          dict(scope="all", target=None, flow="both", multiplier=2.0, start_date="2025-09-04", end_date="2025-09-04", active=True),
          dict(scope="all", target=None, flow="both", multiplier=9.0, start_date="2025-09-01", end_date="2025-09-30", active=False)]
    m = br.event_multipliers(ev, agent, days)
    assert m.shape == (7, 2)
    assert np.allclose(m[0], [1, 1])                  # Sep 2: nothing
    assert np.allclose(m[1], [1.5, 1.0])              # Sep 3: division event, cash-out only
    assert np.allclose(m[2], [3.0, 2.0])              # Sep 4: division x all-agents (multiply)
    assert np.allclose(m[3:], 1.0)                    # other agent's / inactive events ignored
