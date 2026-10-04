"""Dispatch plan + orders (planned vs emergency). Orders are PLANNING RECORDS: a human decides, nothing is autonomous."""
from __future__ import annotations

import math
from collections import defaultdict
from datetime import date

from sqlalchemy import select

from ..errors import ApiError
from ..models import Order
from ..rules import business_rules as br
from .context import Ctx, audit, ledger, now_iso
from .forecasts import get_forecast, summary

FLOW = ["proposed", "acknowledged", "scheduled", "done"]
KINDS = {"cash": "convert e-float to cash", "efloat": "buy e-float with cash"}


def order_dict(o: Order) -> dict:
    return dict(id=o.id, agent_id=o.agent_id, plan_date=o.plan_date, due_date=o.due_date, kind=o.kind, amount=round(o.amount),
                order_type=o.order_type, status=o.status, scheduled_for=o.scheduled_for, note=o.note, created_by=o.created_by,
                created_at=o.created_at, updated_at=o.updated_at, meaning=KINDS[o.kind])


def list_orders(ctx: Ctx, status: str | None = None) -> list[dict]:
    q = select(Order).order_by(Order.id.desc())
    if status:
        q = q.where(Order.status == status)
    return [order_dict(o) for o in ctx.db.scalars(q)]


def dispatch_plan(ctx: Ctx, d: date) -> dict:
    ctx.check_date(d)
    orders = {(o.agent_id, o.kind): o for o in ctx.db.scalars(select(Order).where(Order.plan_date == d.isoformat(), Order.status != "cancelled"))}
    by_div: dict[str, list] = defaultdict(list)
    nxt = None
    for aid in sorted(ledger.agents):
        p = get_forecast(ctx, aid, d)
        s = summary(p)
        nxt = p["cash"]["next_working_day"]
        for kind in ("cash", "efloat"):
            sec = p[kind]
            if sec["topup"] <= 0:
                continue
            o = orders.get((aid, kind))
            by_date = sec["topup_by_date"]
            by_div[s["division"]].append(dict(
                agent_id=aid, division=s["division"], location_type=s["location_type"], kind=kind, meaning=KINDS[kind],
                amount=sec["topup"], by_date=by_date, urgent=by_date <= nxt, order_type=br.order_type(p["status"], dict(late=sec["topup_late"])),
                status=p["status"], risk_pct=sec["risk_pct"], likely_runout_date=sec["likely_runout_date"],
                float_insufficient=s["float_insufficient"], capital_needed=s["capital_needed"],
                order=order_dict(o) if o else None))
    divisions = []
    for div in sorted(by_div):
        items = sorted(by_div[div], key=lambda i: (i["order_type"] != "emergency", not i["urgent"], -i["risk_pct"], i["agent_id"]))
        open_items = [i for i in items if not (i["order"] and i["order"]["status"] == "done")]
        divisions.append(dict(
            division=div, items=items,
            total_cash=round(sum(i["amount"] for i in open_items if i["kind"] == "cash")),
            total_efloat=round(sum(i["amount"] for i in open_items if i["kind"] == "efloat")),
            needs_capital=sorted({i["agent_id"] for i in items if i["float_insufficient"]})))
    if nxt is None:
        nxt = br.next_working_day(d, {}).isoformat()
    return dict(date=d.isoformat(), next_working_day=nxt, divisions=divisions,
                totals=dict(cash=sum(x["total_cash"] for x in divisions), efloat=sum(x["total_efloat"] for x in divisions),
                            orders=sum(1 for x in divisions for i in x["items"] if i["order"]),
                            emergency=sum(1 for x in divisions for i in x["items"] if i["order_type"] == "emergency")),
                note="Recommendations only. A cash top-up converts e-float to cash; an e-float top-up buys e-float with cash.")


def create_order(ctx: Ctx, actor: str, agent_id: str, kind: str, amount: float, due_date: date, order_type: str,
                 status: str = "acknowledged", note: str | None = None) -> dict:
    agent_id = agent_id.upper()
    ctx.agent(agent_id)
    if kind not in KINDS:
        raise ApiError(422, "validation_error", "kind must be 'cash' or 'efloat'")
    if order_type not in ("planned", "emergency"):
        raise ApiError(422, "validation_error", "order_type must be 'planned' or 'emergency'")
    if status not in FLOW[:3]:
        raise ApiError(422, "validation_error", "initial status must be proposed, acknowledged or scheduled")
    if not math.isfinite(amount) or amount <= 0:
        raise ApiError(422, "validation_error", "amount must be a positive number")
    if due_date < ctx.sim_date:
        raise ApiError(422, "validation_error", "due_date cannot be before the simulation date")
    plan = ctx.sim_date.isoformat()
    dup = ctx.db.scalar(select(Order).where(Order.agent_id == agent_id, Order.kind == kind, Order.plan_date == plan, Order.status != "cancelled"))
    if dup:
        raise ApiError(409, "order_exists", "An order for this agent and kind already exists for today's plan", {"order_id": dup.id})
    t = now_iso()
    o = Order(agent_id=agent_id, plan_date=plan, due_date=due_date.isoformat(), kind=kind, amount=float(amount), order_type=order_type,
              status=status, scheduled_for=due_date.isoformat() if status == "scheduled" else None, note=note, created_by=actor,
              created_at=t, updated_at=t)
    ctx.db.add(o)
    ctx.db.flush()
    audit(ctx.db, actor, "order_create", "order", o.id, dict(agent_id=agent_id, kind=kind, amount=amount, order_type=order_type, status=status))
    ctx.db.commit()
    return order_dict(o)


def update_order(ctx: Ctx, actor: str, order_id: int, status: str | None, scheduled_for: date | None, note: str | None) -> dict:
    o = ctx.db.get(Order, order_id)
    if o is None:
        raise ApiError(404, "not_found", "Order not found")
    before = dict(status=o.status, scheduled_for=o.scheduled_for)
    if status is not None:
        if status == "cancelled":
            if o.status == "done":
                raise ApiError(409, "invalid_transition", "A completed order cannot be cancelled")
        elif status not in FLOW:
            raise ApiError(422, "validation_error", "status must be one of " + ", ".join(FLOW + ["cancelled"]))
        elif o.status in ("done", "cancelled") or FLOW.index(status) <= FLOW.index(o.status):
            raise ApiError(409, "invalid_transition", f"Cannot move an order from {o.status} to {status}")
        o.status = status
    if scheduled_for is not None:
        if scheduled_for < ctx.sim_date:
            raise ApiError(422, "validation_error", "scheduled_for cannot be before the simulation date")
        o.scheduled_for = scheduled_for.isoformat()
        if o.status in ("proposed", "acknowledged"):
            o.status = "scheduled"
    if note is not None:
        o.note = note[:200]
    o.updated_at = now_iso()
    audit(ctx.db, actor, "order_update", "order", o.id, dict(before=before, after=dict(status=o.status, scheduled_for=o.scheduled_for)))
    ctx.db.commit()
    return order_dict(o)
