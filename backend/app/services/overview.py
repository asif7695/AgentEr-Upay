"""Admin overview: risk-ranked agents, KPI tiles, division summary."""
from __future__ import annotations

from collections import defaultdict
from datetime import date

from sqlalchemy import func, select

from ..models import Alert, Order
from ..rules import business_rules as br
from .context import Ctx, ledger
from .forecasts import get_forecast, summary


def overview(ctx: Ctx, d: date) -> dict:
    ctx.check_date(d)
    rows = [summary(get_forecast(ctx, aid, d)) for aid in sorted(ledger.agents)]
    rows.sort(key=br.rank_key)
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    done = {(o.agent_id, o.kind) for o in ctx.db.scalars(select(Order).where(Order.plan_date == d.isoformat(), Order.status == "done"))}
    planned_cash = sum(r["topup_cash"] for r in rows if (r["agent_id"], "cash") not in done)
    planned_ef = sum(r["topup_efloat"] for r in rows if (r["agent_id"], "efloat") not in done)
    kpis = dict(
        high=sum(r["status"] == "HIGH" for r in rows), watch=sum(r["status"] == "WATCH" for r in rows), ok=sum(r["status"] == "OK" for r in rows),
        expected_unserved=round(sum(r["expected_unserved"] for r in rows)),
        planned_topup_cash=round(planned_cash), planned_topup_efloat=round(planned_ef), planned_topup_total=round(planned_cash + planned_ef),
        agents_needing_capital=sum(r["float_insufficient"] for r in rows),
        reports_missing=sum(r["report_status"] in ("missing", "pending") for r in rows),
        reports_flagged=sum(r["report_status"] == "needs_verification" for r in rows),
        open_alerts=ctx.db.scalar(select(func.count()).select_from(Alert).where(Alert.status == "open")) or 0,
    )
    divs: dict[str, dict] = defaultdict(lambda: dict(agents=0, high=0, watch=0, ok=0, topup_total=0.0, worst="OK", agent_ids=[]))
    for r in rows:
        x = divs[r["division"]]
        x["agents"] += 1
        x[r["status"].lower()] += 1
        x["topup_total"] += r["topup_cash"] + r["topup_efloat"]
        x["worst"] = br.worst_status(x["worst"], r["status"])
        x["agent_ids"].append(r["agent_id"])
    divisions = [dict(division=k, **{**v, "topup_total": round(v["topup_total"])}) for k, v in sorted(divs.items())]
    return dict(date=d.isoformat(), kpis=kpis, agents=rows, divisions=divisions,
                thresholds=dict(high=ctx.rules["high_threshold"], watch=ctx.rules["watch_threshold"]),
                note="Expected unserved demand is a model estimate inside each agent's coverage window (Monte Carlo), not ground truth.")
