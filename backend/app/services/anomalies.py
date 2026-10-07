"""Unusual-event detection (adaptive decision intelligence, slice 2).

Every night the model's one-day-ahead forecast for the day that just ended is compared with what the ledger recorded
(ledger rows up to the simulation date only). A jump or a sustained shift for one agent becomes a proposed agent event; when
at least half of a division's agents (and at least two) move the same way on the same day it becomes ONE proposed area
event. Accepting a proposal creates an ordinary demand-multiplier event for the coming week, so the rest of the app (forecast,
risk, dispatch) needs no special case. Auto mode accepts only small adjustments (bounded multiplier); anything larger waits
for a person. All of it is recommendation-grade, audit-logged and reversible.
"""
from __future__ import annotations

import json
import math
from collections import defaultdict
from datetime import date, timedelta
from statistics import median

import numpy as np
import pandas as pd
from sqlalchemy import select

from ..errors import ApiError
from ..ml import anomaly
from ..ml import liquidity_forecaster as lf
from ..ml.model_store import effective_model
from ..models import DetectedEvent, Event
from . import adaptive
from .alerts import add_alert
from .context import Ctx, audit, event_dict, ledger, now_iso

LOOKBACK = 21            # days of one-day-ahead forecasts compared with outcomes
AUTO_MAX_MULT = 1.6      # auto mode applies multipliers inside [1/1.6, 1.6]; beyond that a person decides
HORIZON = lf.H           # an accepted event covers the next 7 forecast days


def detect_agent(ctx: Ctx, agent_id: str, d: date) -> list[dict]:
    """Detections for the day d (the target of the one-day-ahead forecast made at d-1). Uses only ledger rows <= d."""
    model = effective_model(ctx.rules["model_choice"])
    rows = adaptive._origin_rows(model, agent_id, d)
    rows = [r for r in rows if r[0] + timedelta(days=1) <= pd.Timestamp(d)][-LOOKBACK:]
    if len(rows) < 8 or rows[-1][0] + timedelta(days=1) != pd.Timestamp(d):
        return []
    g = ledger.frames[agent_id]
    flags = g[g["date"] <= pd.Timestamp(d)].set_index("date")[["cash_stockout", "efloat_stockout"]].astype(bool).to_dict("index")
    found = []
    for flow, key, so_col, qi in (("cashout", "y_co", "cash_stockout", 0), ("cashin", "y_ci", "efloat_stockout", 1)):
        y = [float(r[1][key].to_numpy()[0]) for r in rows]
        q = [r[2 + qi][0] for r in rows]
        cen = [flags[r[0] + timedelta(days=1)][so_col] for r in rows]
        det = anomaly.detect_flow(y, q, cen)
        if det:
            found.append(dict(det, flow=flow, agent_id=agent_id))
    return found


def _merge_flows(dets: list[dict]) -> list[dict]:
    """Same agent, same direction on both flows -> one 'both' detection (multiplier = mean)."""
    out, used = [], set()
    for i, a in enumerate(dets):
        if i in used:
            continue
        for j in range(i + 1, len(dets)):
            b = dets[j]
            if j not in used and a["agent_id"] == b["agent_id"] and a["direction"] == b["direction"] and a["flow"] != b["flow"]:
                out.append(dict(a, flow="both", multiplier=round((a["multiplier"] + b["multiplier"]) / 2, 2), kind="shift" if "shift" in (a["kind"], b["kind"]) else "jump",
                                cusum=max(a["cusum"], b["cusum"])))
                used.update((i, j))
                break
        else:
            out.append(a)
    return out


def _overlaps(ctx: Ctx, scope: str, target: str, flow: str, start: date, end: date) -> bool:
    q = select(DetectedEvent).where(DetectedEvent.scope == scope, DetectedEvent.target == target, DetectedEvent.status.in_(("proposed", "accepted")),
                                    DetectedEvent.end_date >= start.isoformat(), DetectedEvent.start_date <= end.isoformat())
    return any(e.flow in (flow, "both") or flow == "both" for e in ctx.db.scalars(q))


def _plan(ctx: Ctx, d: date) -> list[dict]:
    """Candidate proposals for night d: agent events plus folded area events."""
    per_agent: list[dict] = []
    for aid in sorted(ledger.agents):
        per_agent += _merge_flows(detect_agent(ctx, aid, d))
    by_div: dict[str, list[dict]] = defaultdict(list)
    for x in per_agent:
        by_div[ledger.agents[x["agent_id"]]["division"]].append(x)
    sizes: dict[str, int] = defaultdict(int)
    for a in ledger.agents.values():
        sizes[a["division"]] += 1
    plans, folded = [], set()
    for div, items in by_div.items():
        for flow in ("both", "cashout", "cashin"):
            for direction in ("up", "down"):
                grp = [x for x in items if x["flow"] == flow and x["direction"] == direction]
                if len(grp) >= max(2, math.ceil(0.5 * sizes[div])):
                    plans.append(dict(scope="division", target=div, flow=flow, direction=direction, kind="shift" if any(x["kind"] == "shift" for x in grp) else "jump",
                                      multiplier=round(median(x["multiplier"] for x in grp), 2), members=grp))
                    folded.update(id(x) for x in grp)
    for x in per_agent:
        if id(x) not in folded:
            plans.append(dict(scope="agent", target=x["agent_id"], flow=x["flow"], direction=x["direction"], kind=x["kind"], multiplier=x["multiplier"], members=[x]))
    return plans


def _accept(ctx: Ctx, de: DetectedEvent, actor: str) -> None:
    flow = de.flow
    ev = Event(scope=de.scope, target=de.target, kind="detected", flow=flow, multiplier=de.multiplier, start_date=de.start_date, end_date=de.end_date,
               note=f"Detected {de.kind} ({de.direction}); accepted by {actor}"[:200], active=True, created_by=actor, created_at=now_iso())
    ctx.db.add(ev)
    ctx.db.flush()
    de.event_id, de.status, de.decided_by, de.decided_at = ev.id, "accepted", actor, now_iso()
    ctx.events.append(event_dict(ev))
    audit(ctx.db, actor, "detected_event_accept", "detected_event", de.id, dict(event_id=ev.id, scope=de.scope, target=de.target, multiplier=de.multiplier))


def run_nightly(ctx: Ctx, d: date, actor: str = "system") -> dict:
    mode = ctx.rules["adaptive_mode"]
    # proposals whose window has passed expire quietly
    for de in ctx.db.scalars(select(DetectedEvent).where(DetectedEvent.status == "proposed", DetectedEvent.end_date < d.isoformat())):
        de.status = "expired"
    if mode == "off":
        return dict(mode=mode, proposed=0, accepted=0)
    start, end = d + timedelta(days=1), d + timedelta(days=HORIZON)
    proposed = accepted = 0
    for p in _plan(ctx, d):
        if _overlaps(ctx, p["scope"], p["target"], p["flow"], start, end):
            continue
        ev = dict(members=[dict(agent_id=m["agent_id"], flow=m["flow"], kind=m["kind"], days=m["days"], z_last=m["z_last"], cusum=m["cusum"],
                                raw_ratio=m["raw_ratio"], multiplier=m["multiplier"]) for m in p["members"]],
                  protocol="one-day-ahead model forecast vs ledger; jump = 2 days with |z|>=1.64 and >=25% off the median, or CUSUM(k=0.75,h=5) over 14 days with >=3 days; "
                           "censored (stock-out) days only confirm upward moves; proposed multiplier = 70% of the gap")
        de = DetectedEvent(scope=p["scope"], target=p["target"], flow=p["flow"], kind=p["kind"], direction=p["direction"], multiplier=p["multiplier"],
                           start_date=start.isoformat(), end_date=end.isoformat(), evidence=json.dumps(ev), status="proposed", created_date=d.isoformat(),
                           created_at=now_iso())
        ctx.db.add(de)
        ctx.db.flush()
        audit(ctx.db, actor, "detected_event_propose", "detected_event", de.id, dict(scope=de.scope, target=de.target, flow=de.flow, kind=de.kind, multiplier=de.multiplier))
        proposed += 1
        for m in p["members"]:
            pct = round(100 * (m["multiplier"] - 1))
            add_alert(ctx, m["agent_id"], d, "event_detected", "watch",
                      f"{m['agent_id']}: demand is running {abs(pct)}% {'above' if pct > 0 else 'below'} the forecast ({m['kind']}). A demand adjustment is proposed for review.",
                      dict(pct=pct))
        if mode == "auto" and 1 / AUTO_MAX_MULT <= de.multiplier <= AUTO_MAX_MULT:
            _accept(ctx, de, "system")
            accepted += 1
    return dict(mode=mode, proposed=proposed, accepted=accepted)


def decide(ctx: Ctx, actor: str, detected_id: int, action: str) -> dict:
    de = ctx.db.get(DetectedEvent, detected_id)
    if de is None:
        raise ApiError(404, "not_found", "Detected event not found")
    if action == "accept":
        if de.status != "proposed":
            raise ApiError(409, "invalid_transition", f"A {de.status} proposal cannot be accepted")
        if de.end_date < ctx.sim_date.isoformat():
            raise ApiError(409, "expired", "This proposal's window has passed")
        _accept(ctx, de, actor)
    elif action == "dismiss":
        if de.status != "proposed":
            raise ApiError(409, "invalid_transition", f"A {de.status} proposal cannot be dismissed")
        de.status, de.decided_by, de.decided_at = "dismissed", actor, now_iso()
        audit(ctx.db, actor, "detected_event_dismiss", "detected_event", de.id, {})
    elif action == "revoke":
        if de.status != "accepted" or de.event_id is None:
            raise ApiError(409, "invalid_transition", "Only an accepted proposal can be revoked")
        ev = ctx.db.get(Event, de.event_id)
        if ev is not None:
            ev.active = False
        de.status, de.decided_by, de.decided_at = "revoked", actor, now_iso()
        audit(ctx.db, actor, "detected_event_revoke", "detected_event", de.id, dict(event_id=de.event_id))
    else:
        raise ApiError(422, "validation_error", "action must be accept, dismiss or revoke")
    ctx.db.commit()
    return de_dict(de)


def de_dict(e: DetectedEvent) -> dict:
    return dict(id=e.id, scope=e.scope, target=e.target, flow=e.flow, kind=e.kind, direction=e.direction, multiplier=e.multiplier,
                start_date=e.start_date, end_date=e.end_date, evidence=json.loads(e.evidence), status=e.status, event_id=e.event_id,
                created_date=e.created_date, decided_by=e.decided_by, decided_at=e.decided_at)


def listing(ctx: Ctx, limit: int = 60) -> list[dict]:
    return [de_dict(e) for e in ctx.db.scalars(select(DetectedEvent).order_by(DetectedEvent.id.desc()).limit(limit))]


def evaluate_shocks(ctx: Ctx, trials: list[dict], d_max: date) -> list[dict]:
    """Shock-injection test (offline evidence): multiplies an agent's observed flows by `mult` for `length` days from `start`,
    then asks the detector, night by night, whether it noticed. Restores the ledger afterwards."""
    results = []
    orig = ledger.frames
    try:
        for t in trials:
            frames = {a: f.copy() for a, f in orig.items()}
            fr = frames[t["agent_id"]]
            win = (fr["date"] >= pd.Timestamp(t["start"])) & (fr["date"] < pd.Timestamp(t["start"]) + timedelta(days=t["length"]))
            for col in ("observed_cashout", "observed_cashin"):
                fr.loc[win, col] = fr.loc[win, col] * t["mult"]
            ledger.frames = frames
            adaptive.invalidate(t["agent_id"], pd.Timestamp(t["start"]).date())
            delay = None
            for k in range(0, t["length"] + 3):
                d = pd.Timestamp(t["start"]).date() + timedelta(days=k)
                if d > d_max:
                    break
                dets = [x for x in detect_agent(ctx, t["agent_id"], d) if x["direction"] == ("up" if t["mult"] > 1 else "down")]
                if dets:
                    delay = k
                    break
            results.append(dict(t, detected=delay is not None, delay_days=delay))
            ledger.frames = orig
            adaptive.invalidate(t["agent_id"], pd.Timestamp(t["start"]).date())
    finally:
        ledger.frames = orig
    return results
