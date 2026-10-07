"""Network-wide allocation (admin): optimised daily plan under the distributor's budgets, with locks / overrides and an explicit approve step."""
from __future__ import annotations

from datetime import date as Date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import get_db
from ..errors import ApiError
from ..models import User
from ..rules import allocation_rules as ar
from ..rules import business_rules as br
from ..services import allocation
from ..services.context import Ctx, audit, set_config

router = APIRouter(tags=["allocation"])


class SettingsPatch(BaseModel):
    cash_budget: float | None = Field(default=None, allow_inf_nan=False)
    efloat_budget: float | None = Field(default=None, allow_inf_nan=False)
    max_orders_per_division: int | None = None
    protect_high_risk: bool | None = None


class PlanIn(BaseModel):
    locks: dict[str, float] = Field(default_factory=dict, description="line key ('A01:cash') -> fixed amount; 0 = no order")
    settings: SettingsPatch | None = Field(default=None, description="what-if budgets for this solve only (not saved)")


def _body_settings(ctx: Ctx, body: PlanIn) -> dict | None:
    if body.settings is None:
        return None
    try:
        return ar.validate_allocation(body.settings.model_dump(exclude_none=True), ctx.rules["allocation"])
    except ValueError as e:
        raise ApiError(422, "validation_error", str(e))


@router.get("/admin/allocation")
def get_plan(date: Date | None = None, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    ctx = Ctx(db)
    return dict(allocation.plan(ctx, date or ctx.sim_date), bounds=ar.ALLOCATION_BOUNDS, defaults=ar.DEFAULT_ALLOCATION)


@router.post("/admin/allocation/solve")
def solve(body: PlanIn, _: User = Depends(require_admin), db: Session = Depends(get_db)):
    ctx = Ctx(db)
    return allocation.plan(ctx, ctx.sim_date, settings=_body_settings(ctx, body), locks=body.locks)


@router.put("/admin/allocation/settings")
def put_settings(body: SettingsPatch, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    ctx = Ctx(db)
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise ApiError(422, "validation_error", "No changes supplied")
    try:
        merged = br.validate_rules({"allocation": ar.validate_allocation(patch, ctx.rules["allocation"])}, ctx.rules)
    except ValueError as e:
        raise ApiError(422, "validation_error", str(e))
    set_config(db, "allocation", merged["allocation"])
    audit(db, user.username, "allocation_settings", "config", None, {k: dict(old=ctx.rules["allocation"][k], new=merged["allocation"][k]) for k in patch})
    db.commit()
    ctx = Ctx(db)
    return dict(allocation.plan(ctx, ctx.sim_date), bounds=ar.ALLOCATION_BOUNDS, defaults=ar.DEFAULT_ALLOCATION)


@router.post("/admin/allocation/approve")
def approve(body: PlanIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    ctx = Ctx(db)
    return allocation.approve(ctx, user.username, ctx.sim_date, body.locks)
