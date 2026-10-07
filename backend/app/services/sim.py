"""Simulation clock + the 'nightly pipeline' (ingest ledger -> request reports -> recompute forecasts -> raise alerts)."""
from __future__ import annotations

import time
from datetime import date, timedelta

from sqlalchemy.orm import Session

from .. import settings
from ..errors import ApiError
from . import adaptive, anomalies
from .alerts import raise_alerts
from .context import Ctx, audit, ledger, set_config

MIN_D = date.fromisoformat(settings.SIM_MIN_DATE)
MAX_D = date.fromisoformat(settings.SIM_MAX_DATE)


def state(ctx: Ctx) -> dict:
    d = ctx.sim_date
    return dict(date=d.isoformat(), weekday=d.strftime("%A"), min_date=settings.SIM_MIN_DATE, max_date=settings.SIM_MAX_DATE,
                reveal_max_date=settings.REVEAL_MAX_DATE, can_advance=d < MAX_D, can_reveal=d <= date.fromisoformat(settings.REVEAL_MAX_DATE),
                synthetic_data=True)


def run_pipeline(ctx: Ctx, d: date) -> dict:
    t0 = time.perf_counter()
    ingested = sum(1 for aid in ledger.agents if ledger.row(aid, d) is not None)
    requested = [a for a in ledger.agents if a in ctx.rules["manual_report_agents"]]
    adapt = adaptive.run_nightly(ctx, d)       # per-agent adaptations first, so tonight's forecasts and alerts already use them
    events = anomalies.run_nightly(ctx, d)     # unusual-demand detection: proposals (or small auto-accepts) before forecasts are refreshed
    created = raise_alerts(ctx, d)          # also recomputes (and caches) every agent's forecast for d
    ctx.db.commit()
    return dict(date=d.isoformat(), ledger_rows_ingested=ingested, reports_requested=len(requested),
                forecasts_recomputed=len(ledger.agents), alerts_created=created, adaptive=adapt, detected_events=events, elapsed_ms=round(1000 * (time.perf_counter() - t0)))


def _move(db: Session, actor: str, target: date, action: str) -> dict:
    ctx = Ctx(db)
    prev = ctx.sim_date
    set_config(db, "sim_date", target.isoformat())
    ctx.sim_date = target
    ctx._reports.clear()
    audit(db, actor, action, "sim_clock", None, {"from": prev.isoformat(), "to": target.isoformat()})
    db.commit()
    steps = run_pipeline(ctx, target)
    return dict(state=state(ctx), pipeline=steps)


def advance(db: Session, actor: str) -> dict:
    ctx = Ctx(db)
    if ctx.sim_date >= MAX_D:
        raise ApiError(409, "end_of_data", "The dataset ends on " + settings.SIM_MAX_DATE)
    return _move(db, actor, ctx.sim_date + timedelta(days=1), "advance")


def jump(db: Session, actor: str, target: date) -> dict:
    if target < MIN_D or target > MAX_D:
        raise ApiError(422, "date_out_of_range", f"Date must be between {settings.SIM_MIN_DATE} and {settings.SIM_MAX_DATE}")
    return _move(db, actor, target, "jump")
