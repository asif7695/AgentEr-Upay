"""Admin endpoints: overview, dispatch plan, orders, rules, events, alerts, audit."""
from __future__ import annotations

import json
from datetime import date as Date
from typing import Literal

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import settings
from ..auth import current_user, require_admin
from ..db import get_db
from ..errors import ApiError
from ..ml.model_store import default_risk_config
from ..models import Alert, AuditLog, Event, User
from ..rules import business_rules as br
from ..services import dispatch, overview as overview_svc
from ..services.alerts import alert_dict
from ..services.context import Ctx, audit, event_dict, ledger, now_iso, set_config

router = APIRouter(tags=["admin"])


class OrderIn(BaseModel):
    agent_id: str = Field(min_length=2, max_length=8)
    kind: Literal["cash", "efloat"]
    amount: float = Field(gt=0, le=100_000_000, allow_inf_nan=False)
    due_date: Date
    order_type: Literal["planned", "emergency"] = "planned"
    status: Literal["proposed", "acknowledged", "scheduled"] = "acknowledged"
    note: str | None = Field(default=None, max_length=200)


class OrderPatch(BaseModel):
    status: Literal["proposed", "acknowledged", "scheduled", "done", "cancelled"] | None = None
    scheduled_for: Date | None = None
    note: str | None = Field(default=None, max_length=200)


class ConfigPatch(BaseModel):
    buffer_frac: float | None = Field(default=None, allow_inf_nan=False)
    coverage_prob: float | None = Field(default=None, allow_inf_nan=False)
    min_order_frac: float | None = Field(default=None, allow_inf_nan=False)
    high_threshold: float | None = Field(default=None, allow_inf_nan=False)
    watch_threshold: float | None = Field(default=None, allow_inf_nan=False)
    recon_tolerance: float | None = Field(default=None, allow_inf_nan=False)
    dependence_mode: Literal["t_copula", "correlated", "ar1", "independent"] | None = None
    model_choice: Literal["challenger", "reference"] | None = None
    manual_report_agents: list[str] | None = None


class EventIn(BaseModel):
    scope: Literal["all", "division", "agent"]
    target: str | None = Field(default=None, max_length=32)
    kind: Literal["fair", "road_closure", "flood", "other"]
    flow: Literal["both", "cashout", "cashin"] = "both"
    multiplier: float = Field(ge=0.1, le=5.0, allow_inf_nan=False)
    start_date: Date
    end_date: Date
    note: str | None = Field(default=None, max_length=200)


@router.get("/admin/model-evidence")
def model_evidence(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Model-development evidence (comparison, calibration, unseen agents/events, path dependence). Static, offline, synthetic."""
    path = settings.BACKEND / "app" / "data" / "model_evidence.json"
    if not path.exists():
        raise ApiError(404, "not_found", "Run `python -m ml_train.run main unseen paths assemble` to generate the evidence")
    ctx = Ctx(db)
    return dict(json.loads(path.read_text(encoding="utf-8")), active=dict(model_choice=ctx.rules["model_choice"], dependence_mode=ctx.rules["dependence_mode"]))


@router.get("/admin/overview")
def overview(date: Date | None = None, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    ctx = Ctx(db)
    return overview_svc.overview(ctx, date or ctx.sim_date)


@router.get("/admin/dispatch-plan")
def dispatch_plan(date: Date | None = None, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    ctx = Ctx(db)
    return dispatch.dispatch_plan(ctx, date or ctx.sim_date)


@router.get("/admin/orders")
def list_orders(status: str | None = Query(None, max_length=12), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    return dispatch.list_orders(Ctx(db), status)


@router.post("/admin/orders", status_code=201)
def create_order(body: OrderIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return dispatch.create_order(Ctx(db), user.username, body.agent_id, body.kind, body.amount, body.due_date, body.order_type,
                                 body.status, body.note)


@router.patch("/admin/orders/{order_id}")
def patch_order(order_id: int, body: OrderPatch, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return dispatch.update_order(Ctx(db), user.username, order_id, body.status, body.scheduled_for, body.note)


def _config_view(ctx: Ctx) -> dict:
    base = default_risk_config()
    return dict(rules=ctx.rules, config_hash=br.config_hash(ctx.rules), bounds=br.RULE_BOUNDS,
                defaults=br.DEFAULT_RULES, model_risk_config=base,
                note="Rules are applied on a COPY of the bundle's risk_config. The model is never retrained or modified.")


@router.get("/admin/config")
def get_config(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _config_view(Ctx(db))


@router.put("/admin/config")
def put_config(body: ConfigPatch, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    ctx = Ctx(db)
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise ApiError(422, "validation_error", "No changes supplied")
    try:
        merged = br.validate_rules(patch, ctx.rules)
    except ValueError as e:
        raise ApiError(422, "validation_error", str(e))
    changed = {k: dict(old=ctx.rules[k], new=merged[k]) for k in merged if merged[k] != ctx.rules[k]}
    for k in changed:
        set_config(db, k, merged[k])
    audit(db, user.username, "config_update", "config", None, changed)
    db.commit()
    return _config_view(Ctx(db))


@router.get("/admin/events")
def list_events(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    ctx = Ctx(db)
    return [dict(event_dict(e), label="manual adjustment, not learned by the model")
            for e in db.scalars(select(Event).order_by(Event.id.desc()))]


@router.post("/admin/events", status_code=201)
def create_event(body: EventIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    ctx = Ctx(db)
    if body.end_date < body.start_date:
        raise ApiError(422, "validation_error", "end_date must not be before start_date")
    if (body.end_date - body.start_date).days > 60:
        raise ApiError(422, "validation_error", "An event can span at most 61 days")
    target = body.target.strip() if body.target else None
    if body.scope == "agent":
        target = (target or "").upper()
        if target not in ledger.agents:
            raise ApiError(422, "validation_error", "Unknown agent")
    elif body.scope == "division":
        if target not in {a["division"] for a in ledger.agents.values()}:
            raise ApiError(422, "validation_error", "Unknown division")
    else:
        target = None
    e = Event(scope=body.scope, target=target, kind=body.kind, flow=body.flow, multiplier=body.multiplier,
              start_date=body.start_date.isoformat(), end_date=body.end_date.isoformat(), note=body.note, active=True,
              created_by=user.username, created_at=now_iso())
    db.add(e)
    db.flush()
    audit(db, user.username, "event_create", "event", e.id, event_dict(e))
    db.commit()
    return dict(event_dict(e), label="manual adjustment, not learned by the model")


@router.delete("/admin/events/{event_id}")
def deactivate_event(event_id: int, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    e = db.get(Event, event_id)
    if e is None:
        raise ApiError(404, "not_found", "Event not found")
    e.active = False
    audit(db, user.username, "event_deactivate", "event", e.id, {})
    db.commit()
    return dict(event_dict(e), label="manual adjustment, not learned by the model")


@router.get("/admin/audit")
def audit_log(limit: int = Query(50, ge=1, le=500), _: User = Depends(require_admin), db: Session = Depends(get_db)):
    rows = db.scalars(select(AuditLog).order_by(AuditLog.id.desc()).limit(limit))
    return [dict(id=r.id, ts=r.ts, actor=r.actor, action=r.action, entity=r.entity, entity_id=r.entity_id, detail=json.loads(r.detail)) for r in rows]


# ---- alerts (admin sees all; an agent sees only their own) ----
@router.get("/alerts")
def list_alerts(status: Literal["open", "acked"] | None = None, agent_id: str | None = Query(None, max_length=8),
                limit: int = Query(100, ge=1, le=500), user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(Alert).order_by(Alert.date.desc(), Alert.id.desc()).limit(limit)
    if user.role == "agent":
        q = q.where(Alert.agent_id == user.agent_id)
    elif agent_id:
        q = q.where(Alert.agent_id == agent_id.upper())
    if status:
        q = q.where(Alert.status == status)
    return [alert_dict(a) for a in db.scalars(q)]


@router.post("/alerts/{alert_id}/ack")
def ack_alert(alert_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = db.get(Alert, alert_id)
    if a is None or (user.role == "agent" and a.agent_id != user.agent_id):
        raise ApiError(404, "not_found", "Alert not found")        # same answer for 'not yours': no existence leak
    if a.status != "acked":
        a.status, a.acked_by, a.acked_at = "acked", user.username, now_iso()
        audit(db, user.username, "alert_ack", "alert", a.id, dict(agent_id=a.agent_id, type=a.type))
        db.commit()
    return alert_dict(a)
