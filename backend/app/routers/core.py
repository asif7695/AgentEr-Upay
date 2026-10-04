"""Auth, session, sim clock, health, impact."""
from __future__ import annotations

import json
from datetime import date as Date
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import create_token, current_user, require_admin, user_public, verify_password
from ..db import get_db
from ..errors import ApiError
from ..ml.model_store import bundle_info
from ..models import User
from ..services import forecasts, sim
from ..services.context import Ctx, audit

router = APIRouter()
_IMPACT = Path(__file__).resolve().parents[1] / "data" / "impact.json"


class LoginIn(BaseModel):
    username: str = Field(min_length=1, max_length=32)
    password: str = Field(min_length=1, max_length=128)


class JumpIn(BaseModel):
    date: Date


@router.post("/auth/login", tags=["auth"])
def login(body: LoginIn, db: Session = Depends(get_db)):
    uname = body.username.strip().lower()
    if uname.startswith("agent"):                    # "Agent A01", "agent a01", "A01" and "a01" all identify the same agent
        uname = uname[5:].strip()
    user = db.scalar(select(User).where(User.username == uname))
    if user is None or not verify_password(body.password, user.password_hash):
        audit(db, body.username[:32], "login_failed", "user", None, {})
        db.commit()
        raise ApiError(401, "invalid_credentials", "Wrong username or password")
    return {"access_token": create_token(user), "token_type": "bearer", "user": user_public(user)}


@router.get("/me", tags=["auth"])
def me(user: User = Depends(current_user)):
    return user_public(user)


@router.get("/sim/state", tags=["sim"])
def sim_state(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return sim.state(Ctx(db))


@router.post("/sim/advance", tags=["sim"])
def sim_advance(user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return sim.advance(db, user.username)


@router.post("/sim/jump", tags=["sim"])
def sim_jump(body: JumpIn, user: User = Depends(require_admin), db: Session = Depends(get_db)):
    return sim.jump(db, user.username, body.date)


@router.get("/health", tags=["system"])
def health(db: Session = Depends(get_db)):
    ctx = Ctx(db)
    return dict(status="ok", model=bundle_info(), sim_date=ctx.sim_date.isoformat(), cache=dict(forecasts.STATS),
                synthetic_data=True)


@router.get("/impact", tags=["impact"])
def impact(_: User = Depends(current_user)):
    data = json.loads(_IMPACT.read_text(encoding="utf-8"))
    pol = {p["key"]: p for p in data["policy_replay"]["policies"]}
    h, y, m = pol["habit"], pol["hybrid"], pol["model_only"]
    pct = lambda a, b: round(100 * (a - b) / b, 1)
    data["policy_replay"]["deltas"] = dict(
        hybrid_vs_habit=dict(stockout_days_pct=pct(y["stockout_days"], h["stockout_days"]), unserved_pct=pct(y["unserved_bdt"], h["unserved_bdt"]),
                             orders_pct=pct(y["orders"], h["orders"])),
        model_only_vs_habit=dict(stockout_days_pct=pct(m["stockout_days"], h["stockout_days"]), unserved_pct=pct(m["unserved_bdt"], h["unserved_bdt"]),
                                 orders_pct=pct(m["orders"], h["orders"])))
    return data
