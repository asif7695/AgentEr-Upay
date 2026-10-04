"""Agent-facing endpoints. Every path with {agent_id} is role-checked via authorize_agent (agents: own data only)."""
from __future__ import annotations

import math
from datetime import date as Date

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import authorize_agent, current_user, require_admin
from ..db import get_db
from ..errors import ApiError
from ..models import Report, User
from ..rules.business_rules import reconcile
from ..services import forecasts, reveal as reveal_svc
from ..services.alerts import alerts_for_payload
from ..services.context import Ctx, audit, ledger, now_iso

router = APIRouter(tags=["agents"])


class CashReportIn(BaseModel):
    cash: float = Field(ge=0, le=1_000_000_000, allow_inf_nan=False, description="Counted physical cash in BDT")
    date: Date | None = None


@router.get("/agents")
def list_agents(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    ctx = Ctx(db)
    return [dict(agent_id=a["agent_id"], division=a["division"], location_type=a["location_type"],
                 capacity_cash=a["capacity_cash"], capacity_efloat=a["capacity_efloat"]) for a in ledger.agents.values()]


@router.get("/agents/{agent_id}")
def get_agent(agent_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    aid = authorize_agent(user, agent_id)
    ctx = Ctx(db)
    a = ctx.agent(aid)
    led = ledger.row(aid, ctx.sim_date)
    return dict(agent_id=aid, division=a["division"], location_type=a["location_type"], capacity_cash=a["capacity_cash"],
                capacity_efloat=a["capacity_efloat"], sim_date=ctx.sim_date.isoformat(),
                balances=dict(ledger_cash=round(float(led["closing_cash"])), efloat=round(float(led["closing_efloat"]))),
                reconciliation=ctx.reconciliation(aid, ctx.sim_date), synthetic_data=True)


@router.get("/agents/{agent_id}/forecast")
def get_forecast(agent_id: str, date: Date | None = None, explain: bool = True, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    aid = authorize_agent(user, agent_id)
    ctx = Ctx(db)
    return forecasts.get_forecast(ctx, aid, date or ctx.sim_date, explain=explain)


@router.get("/agents/{agent_id}/history")
def history(agent_id: str, days: int = Query(60, ge=1, le=365), user: User = Depends(current_user), db: Session = Depends(get_db)):
    aid = authorize_agent(user, agent_id)
    ctx = Ctx(db)
    ctx.agent(aid)
    g = ledger.frames[aid]
    g = g[g["date"] <= ctx.sim_date.isoformat()].tail(days)
    reps = {r.date: r for r in db.scalars(select(Report).where(Report.agent_id == aid, Report.date.in_([d.strftime("%Y-%m-%d") for d in g["date"]])))}
    a = ctx.agent(aid)
    rows = []
    for r in g.itertuples():
        ds = r.date.strftime("%Y-%m-%d")
        rec = ctx.reconciliation(aid, r.date.date())
        rows.append(dict(
            date=ds, closing_cash=round(r.closing_cash), closing_efloat=round(r.closing_efloat), cash_topup=round(r.cash_topup),
            efloat_topup=round(r.efloat_topup), cash_stockout=bool(r.cash_stockout), efloat_stockout=bool(r.efloat_stockout),
            cashout=round(r.observed_cashout), cashin=round(r.observed_cashin),
            report=dict(status=rec["status"], label=rec["label"], reported_cash=rec["reported_cash"], gap=rec["gap"], gap_pct=rec["gap_pct"])))
    return dict(agent_id=aid, capacity_cash=a["capacity_cash"], capacity_efloat=a["capacity_efloat"], rows=rows,
                totals=dict(cash_stockout_days=sum(x["cash_stockout"] for x in rows), efloat_stockout_days=sum(x["efloat_stockout"] for x in rows),
                            cash_topups=sum(1 for x in rows if x["cash_topup"] > 0), efloat_topups=sum(1 for x in rows if x["efloat_topup"] > 0)),
                synthetic_data=True)


@router.post("/agents/{agent_id}/cash-report")
def cash_report(agent_id: str, body: CashReportIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    aid = authorize_agent(user, agent_id)
    ctx = Ctx(db)
    ctx.agent(aid)
    if body.date is not None and body.date != ctx.sim_date:
        raise ApiError(422, "validation_error", f"Reports can only be submitted for today ({ctx.sim_date.isoformat()})")
    d = ctx.sim_date
    led = ledger.row(aid, d)
    rec = reconcile(float(led["closing_cash"]), float(body.cash), ctx.rules["recon_tolerance"])
    row = db.scalar(select(Report).where(Report.agent_id == aid, Report.date == d.isoformat()))
    before = None if row is None else dict(reported=row.reported_cash, status=row.status, source=row.source)
    if row is None:
        row = Report(agent_id=aid, date=d.isoformat(), ledger_cash=float(led["closing_cash"]), status=rec["status"], source="agent")
        db.add(row)
    row.reported_cash, row.ledger_cash, row.gap, row.gap_pct = float(body.cash), float(led["closing_cash"]), rec["gap"], rec["gap_pct"]
    row.status, row.source, row.submitted_at = rec["status"], "agent", now_iso()
    audit(db, user.username, "cash_report", "report", f"{aid}:{d.isoformat()}",
          dict(reported=body.cash, ledger=float(led["closing_cash"]), gap_pct=rec["gap_pct"], status=rec["status"], before=before))
    db.commit()
    ctx = Ctx(db)                                              # fresh report cache -> forecast reflects the new count at once
    p = forecasts.get_forecast(ctx, aid, d, explain=False)
    alerts_for_payload(ctx, p, p["status"])                    # may add a neutral 'needs verification' alert
    db.commit()
    gp = None if rec["gap_pct"] is None else round(100 * rec["gap_pct"], 1)
    if rec["flagged"]:
        msg = ("Your count differs from the ledger-implied cash" + (f" by {gp:+.1f}%" if gp is not None else "")
               + ". We marked it as needing verification and used the ledger value for the forecast. A recount may help.")
    else:
        msg = "Thank you. Your count matches the ledger within tolerance and was used for the forecast."
    return dict(reconciliation=p["reconciliation"], message=msg, forecast=p)


@router.get("/agents/{agent_id}/reveal")
def reveal(agent_id: str, date: Date | None = None, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    ctx = Ctx(db)
    return reveal_svc.reveal(ctx, agent_id, date or ctx.sim_date)
