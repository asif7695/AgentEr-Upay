"""DEMO REVEAL (admin only): what actually happened over the 7 days after an origin date.

This is the ONLY module allowed to read the ground_truth table. Everything returned is labelled synthetic.
"""
from __future__ import annotations

from datetime import date, timedelta

import numpy as np
from sqlalchemy import select

from .. import settings
from ..errors import ApiError
from ..models import GroundTruth
from ..rules import business_rules as br
from .context import Ctx, ledger


def reveal(ctx: Ctx, agent_id: str, d: date) -> dict:
    agent_id = agent_id.upper()
    ctx.agent(agent_id)
    ctx.check_date(d)
    if d > date.fromisoformat(settings.REVEAL_MAX_DATE):
        raise ApiError(409, "reveal_unavailable", f"Outcome overlay needs 7 full days of data; last origin is {settings.REVEAL_MAX_DATE}")
    days = [d + timedelta(days=k) for k in range(1, 8)]
    gt = {r.date: r for r in ctx.db.scalars(select(GroundTruth).where(
        GroundTruth.agent_id == agent_id, GroundTruth.date.in_([x.isoformat() for x in days])))}
    origin = ledger.row(agent_id, d)
    cash0, ef0 = float(origin["closing_cash"]), float(origin["closing_efloat"])
    a = ctx.agent(agent_id)
    tco = np.array([gt[x.isoformat()].true_cashout_demand for x in days])
    tci = np.array([gt[x.isoformat()].true_cashin_demand for x in days])
    cum = np.cumsum(tco - tci)
    buf_c, buf_e = br.risk_cfg_overrides(ctx.rules, a["location_type"], a["agent_id"])["buffer_frac"] * a["capacity_cash"], br.risk_cfg_overrides(ctx.rules, a["location_type"], a["agent_id"])["buffer_frac"] * a["capacity_efloat"]
    cf_cash, cf_ef = cash0 - cum, ef0 + cum
    out = []
    for i, x in enumerate(days):
        g, led = gt[x.isoformat()], ledger.row(agent_id, x)
        out.append(dict(
            k=i + 1, date=x.isoformat(), true_cashout=round(g.true_cashout_demand), true_cashin=round(g.true_cashin_demand),
            served_cashout=round(float(led["observed_cashout"])), served_cashin=round(float(led["observed_cashin"])),
            unserved_cashout=round(g.unserved_cashout), unserved_cashin=round(g.unserved_cashin),
            closing_cash=round(float(led["closing_cash"])), closing_efloat=round(float(led["closing_efloat"])),
            cash_topup=round(float(led["cash_topup"])), efloat_topup=round(float(led["efloat_topup"])),
            cash_stockout=bool(led["cash_stockout"]), efloat_stockout=bool(led["efloat_stockout"]),
            no_topup_cash=round(float(cf_cash[i])), no_topup_efloat=round(float(cf_ef[i]))))
    return dict(
        agent_id=agent_id, origin=d.isoformat(), label="Demo reveal: what actually happened (synthetic ground truth)", synthetic_data=True,
        days=out,
        summary=dict(cash_stockout_days=sum(x["cash_stockout"] for x in out), efloat_stockout_days=sum(x["efloat_stockout"] for x in out),
                     unserved_total=sum(x["unserved_cashout"] + x["unserved_cashin"] for x in out),
                     counterfactual_cash_breach=bool((cf_cash < buf_c).any()), counterfactual_efloat_breach=bool((cf_ef < buf_e).any()),
                     counterfactual_note="Balances if no top-up had arrived, computed from the true demand."))
