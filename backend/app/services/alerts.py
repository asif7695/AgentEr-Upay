"""Alert generation (runs inside the nightly pipeline) and helpers. Wording is neutral: gaps are prompts to verify."""
from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy import select

from .. import settings
from ..models import Alert
from ..rules.business_rules import STATUS_RANK
from .context import Ctx, ledger, now_iso
from .forecasts import get_forecast


def add_alert(ctx: Ctx, agent_id: str, d: date, type_: str, severity: str, message: str, params: dict) -> bool:
    exists = ctx.db.scalar(select(Alert.id).where(Alert.agent_id == agent_id, Alert.date == d.isoformat(), Alert.type == type_))
    if exists:
        return False
    ctx.db.add(Alert(agent_id=agent_id, date=d.isoformat(), type=type_, severity=severity, message=message,
                     params=json.dumps(params), status="open", created_at=now_iso()))
    return True


def alerts_for_payload(ctx: Ctx, p: dict, prev_status: str | None) -> int:
    aid, d = p["agent"]["agent_id"], date.fromisoformat(p["as_of"])
    n = 0
    c, e, W = p["cash"]["risk_pct"], p["efloat"]["risk_pct"], p["cash"]["window_days"]
    params = dict(cash_pct=c, efloat_pct=e, window_days=W)
    prev_rank = STATUS_RANK.get(prev_status, -1)
    if p["status"] == "HIGH" and prev_rank < STATUS_RANK["HIGH"]:
        n += add_alert(ctx, aid, d, "risk_high", "high",
                       f"{aid}: HIGH run-out risk before the next possible top-up (cash {c:.0f}%, e-float {e:.0f}%, {W}-day window).", params)
    elif p["status"] == "WATCH" and prev_rank < STATUS_RANK["WATCH"]:
        n += add_alert(ctx, aid, d, "risk_watch", "watch",
                       f"{aid}: WATCH - run-out risk is rising (cash {c:.0f}%, e-float {e:.0f}%, {W}-day window).", params)
    rec = p["reconciliation"]
    if rec["status"] == "missing":
        n += add_alert(ctx, aid, d, "report_missing", "info",
                       f"{aid}: no cash report for {d.isoformat()}. Estimated from the ledger, not confirmed today.", {})
    elif rec["status"] == "pending":
        n += add_alert(ctx, aid, d, "report_requested", "info", f"{aid}: daily cash report requested for {d.isoformat()}.", {})
    elif rec["status"] == "needs_verification":
        gp = round(100 * rec["gap_pct"], 1) if rec["gap_pct"] is not None else None
        n += add_alert(ctx, aid, d, "report_gap", "watch",
                       f"{aid}: reported cash differs from the ledger-implied cash"
                       + (f" by {gp:+.1f}%" if gp is not None else "") + ". Marked for verification; ledger value used.",
                       dict(gap_pct=gp))
    if p["capital"]["insufficient"]:
        n += add_alert(ctx, aid, d, "capital", "watch",
                       f"{aid}: total float may be too small for the coming window; extra capital of about BDT {p['capital']['needed']:,.0f} suggested.",
                       dict(needed=p["capital"]["needed"]))
    return n


def raise_alerts(ctx: Ctx, d: date) -> int:
    """Evaluate all agents at date d (compares with d-1 for risk-status transitions)."""
    created = 0
    prev_d = d - timedelta(days=1)
    for aid in sorted(ledger.agents):
        p = get_forecast(ctx, aid, d)
        prev = None
        if prev_d >= date.fromisoformat(settings.SIM_MIN_DATE):
            prev = get_forecast(ctx, aid, prev_d)["status"]
        created += alerts_for_payload(ctx, p, prev)
    ctx.db.flush()
    return created


def alert_dict(a: Alert) -> dict:
    return dict(id=a.id, agent_id=a.agent_id, date=a.date, type=a.type, severity=a.severity, message=a.message,
                params=json.loads(a.params or "{}"), status=a.status, created_at=a.created_at, acked_by=a.acked_by, acked_at=a.acked_at)
