"""Per-request context + the in-memory ledger store (the ledger is immutable after seeding, so it is cached).

The ledger store holds ONLY safe ledger columns. Ground truth is never loaded here.
"""
from __future__ import annotations

import json
import threading
from datetime import date, datetime, timezone

import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from .. import settings
from ..db import engine
from ..errors import ApiError
from ..models import Agent, AuditLog, ConfigRow, Event, Report
from ..rules.business_rules import DEFAULT_RULES, reconcile

LEDGER_COLS = ["date", "observed_cashout", "observed_cashin", "opening_cash", "closing_cash", "opening_efloat",
               "closing_efloat", "cash_topup", "efloat_topup", "cash_stockout", "efloat_stockout"]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Ledger:
    def __init__(self):
        self.frames: dict[str, pd.DataFrame] = {}
        self.agents: dict[str, dict] = {}
        self._lock = threading.Lock()

    def load(self) -> None:
        with self._lock:
            d = pd.read_sql("select * from daily order by agent_id, date", engine)
            d["date"] = pd.to_datetime(d["date"])
            self.frames = {aid: g[LEDGER_COLS].reset_index(drop=True) for aid, g in d.groupby("agent_id")}
            a = pd.read_sql("select * from agents order by agent_id", engine)
            self.agents = {r["agent_id"]: {k: (v.item() if hasattr(v, "item") else v) for k, v in r.items()}
                           for r in a.to_dict("records")}

    def ensure(self) -> None:
        if not self.frames:
            self.load()

    def row(self, agent_id: str, d: date) -> pd.Series | None:
        g = self.frames[agent_id]
        hit = g[g["date"] == pd.Timestamp(d)]
        return None if hit.empty else hit.iloc[0]

    def history(self, agent_id: str, d: date, n: int = settings.HISTORY_DAYS) -> pd.DataFrame:
        g = self.frames[agent_id]
        return g[g["date"] <= pd.Timestamp(d)].tail(n)[["date", "observed_cashout", "observed_cashin"]].copy()


ledger = Ledger()


def load_rules(db: Session) -> dict:
    rules = dict(DEFAULT_RULES)
    for r in db.scalars(select(ConfigRow)):
        if r.key in rules:
            rules[r.key] = json.loads(r.value)
    return rules


def load_sim_date(db: Session) -> date:
    row = db.get(ConfigRow, "sim_date")
    return date.fromisoformat(json.loads(row.value) if row else settings.SIM_DEFAULT_DATE)


def set_config(db: Session, key: str, value) -> None:
    row = db.get(ConfigRow, key)
    if row is None:
        db.add(ConfigRow(key=key, value=json.dumps(value)))
    else:
        row.value = json.dumps(value)


def audit(db: Session, actor: str, action: str, entity: str, entity_id=None, detail: dict | None = None) -> None:
    db.add(AuditLog(ts=now_iso(), actor=actor, action=action, entity=entity,
                    entity_id=None if entity_id is None else str(entity_id), detail=json.dumps(detail or {}, default=str)))


def event_label(kind: str) -> str:
    if kind == "detected":
        return "detected from the ledger and approved; not learned by the model"
    return "manual adjustment, not learned by the model"


def event_dict(e: Event) -> dict:
    return dict(id=e.id, scope=e.scope, target=e.target, kind=e.kind, flow=e.flow, multiplier=e.multiplier,
                start_date=e.start_date, end_date=e.end_date, note=e.note, active=bool(e.active),
                created_by=e.created_by, created_at=e.created_at)


class Ctx:
    """Everything a service needs for one request: rules, sim clock, active human events, report lookups."""

    def __init__(self, db: Session):
        ledger.ensure()
        self.db = db
        self.rules = load_rules(db)
        self.sim_date = load_sim_date(db)
        self.events = [event_dict(e) for e in db.scalars(select(Event).where(Event.active.is_(True)))]
        self._reports: dict[tuple[str, str], Report | None] = {}

    def agent(self, agent_id: str) -> dict:
        a = ledger.agents.get(agent_id)
        if a is None:
            raise ApiError(404, "not_found", f"Unknown agent {agent_id}")
        return a

    def check_date(self, d: date) -> None:
        if d < date.fromisoformat(settings.SIM_MIN_DATE):
            raise ApiError(422, "date_out_of_range", f"Forecasts need >= 28 days of history; earliest date is {settings.SIM_MIN_DATE}")
        if d > self.sim_date:
            raise ApiError(422, "date_in_future", f"Date is after the simulation clock ({self.sim_date.isoformat()})")

    def report_row(self, agent_id: str, d: date) -> Report | None:
        key = (agent_id, d.isoformat())
        if key not in self._reports:
            self._reports[key] = self.db.scalar(select(Report).where(Report.agent_id == agent_id, Report.date == key[1]))
        return self._reports[key]

    def reconciliation(self, agent_id: str, d: date) -> dict:
        """Effective reconciliation for (agent, date) under the current rules."""
        row = self.report_row(agent_id, d)
        led = ledger.row(agent_id, d)
        if led is None:
            raise ApiError(404, "not_found", f"No ledger data for {agent_id} on {d.isoformat()}")
        reported, pending, source = None, False, None
        if row is not None:
            reported, source = row.reported_cash, row.source
            if row.source == "replay" and agent_id in self.rules["manual_report_agents"] and d == self.sim_date:
                reported, pending = None, True      # the live demo: the agent submits today's count themselves
        rec = reconcile(float(led["closing_cash"]), reported, self.rules["recon_tolerance"], pending)
        rec.update(date=d.isoformat(), source=source, submitted_at=row.submitted_at if row else None)
        return rec
