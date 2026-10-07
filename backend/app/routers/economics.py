"""Unit economics / ROI of replenishment (admin). Recommendations only: applying the optimum is an explicit, audit-logged admin action."""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..db import get_db
from ..errors import ApiError
from ..models import User
from ..rules import business_rules as br, economics as ec
from ..services.context import Ctx, audit, set_config

router = APIRouter(tags=["economics"])


class EconomicsPatch(BaseModel):
    trip_cost: dict[str, float] | None = None
    margin_rate: float | None = Field(default=None, allow_inf_nan=False)
    agent_share: float | None = Field(default=None, allow_inf_nan=False)
    customer_multiplier: float | None = Field(default=None, allow_inf_nan=False)
    capital_cost_annual: float | None = Field(default=None, allow_inf_nan=False)


def _applied(rules: dict) -> dict:
    return {t: dict(coverage=br.risk_cfg_overrides(rules, t)["coverage_prob"], buffer=br.risk_cfg_overrides(rules, t)["buffer_frac"],
                    up=br.topup_mult(rules, t)) for t in ec.TIERS}


def _view(ctx: Ctx) -> dict:
    a = ec.analyse(ctx.rules["economics"], _applied(ctx.rules))
    if not a.get("available"):
        raise ApiError(404, "not_found", "Run `python -m ml_train.run economics` to build the policy replay")
    a["applied"] = _applied(ctx.rules)
    a["defaults"] = ec.DEFAULT_ECONOMICS
    a["bounds"] = dict(**ec.ECON_BOUNDS, trip_cost=ec.TRIP_BOUNDS)
    a["note"] = ("Trip costs, margins and the customer multiplier are ASSUMPTIONS until upay supplies real figures. "
                 "Outcomes come from a replay of the ledger with no ground truth; demand on stock-out days is imputed from the model.")
    return a


@router.get("/admin/economics")
def get_economics(_: User = Depends(require_admin), db: Session = Depends(get_db)):
    return _view(Ctx(db))


@router.put("/admin/economics")
def put_economics(body: EconomicsPatch, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    ctx = Ctx(db)
    patch = body.model_dump(exclude_none=True)
    if not patch:
        raise ApiError(422, "validation_error", "No changes supplied")
    current = ctx.rules["economics"]
    if "trip_cost" in patch:
        patch["trip_cost"] = {**current["trip_cost"], **patch["trip_cost"]}
    try:
        merged = ec.validate_economics(patch, current)
    except ValueError as e:
        raise ApiError(422, "validation_error", str(e))
    set_config(db, "economics", merged)
    audit(db, user.username, "economics_update", "config", None, {k: dict(old=current[k], new=merged[k]) for k in merged if merged[k] != current[k]})
    db.commit()
    return _view(Ctx(db))


@router.post("/admin/economics/apply-optimum")
def apply_optimum(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    """Writes the cost-optimal coverage, safety buffer and order-up-to multiple per tier into the rules (a recommendation the admin confirms)."""
    ctx = Ctx(db)
    opt = ec.optimum_params(ctx.rules["economics"])
    if opt is None:
        raise ApiError(404, "not_found", "Policy replay not built")
    new = dict(coverage_by_tier={t: v["coverage"] for t, v in opt.items()}, buffer_by_tier={t: v["buffer"] for t, v in opt.items()},
               topup_mult_by_tier={t: v["up"] for t, v in opt.items()})
    merged = br.validate_rules(new, ctx.rules)
    changed = {k: dict(old=ctx.rules[k], new=merged[k]) for k in new if merged[k] != ctx.rules[k]}
    for k in changed:
        set_config(db, k, merged[k])
    audit(db, user.username, "economics_apply_optimum", "config", None, changed)
    db.commit()
    return _view(Ctx(db))
