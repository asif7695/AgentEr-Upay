"""DATA PREPARATION ONLY (no model inference here): CSV -> SQLite.

Column policy:
  safe ledger columns        -> `daily`
  reported_cash/report_missing -> `reports` (reconciled with the rules in rules/business_rules.py)
  true_* / unserved_*          -> `ground_truth` (isolated, read only by the admin Demo-reveal service)
  base_cashout/base_cashin/noise_std (generator internals) -> NEVER loaded
"""
from __future__ import annotations

import json
from datetime import datetime, timezone

import pandas as pd
from sqlalchemy import select, text

from . import settings
from .auth import hash_password
from .db import Base, SessionLocal, engine
from .models import Agent, ConfigRow, User
from .rules.business_rules import DEFAULT_RULES, reconcile

DAILY_COLS = ["agent_id", "date", "observed_cashout", "observed_cashin", "opening_cash", "closing_cash",
              "opening_efloat", "closing_efloat", "cash_topup", "efloat_topup", "cash_stockout", "efloat_stockout"]
TRUTH_COLS = ["agent_id", "date", "true_cashout_demand", "true_cashin_demand", "unserved_cashout", "unserved_cashin"]
AGENT_COLS = ["agent_id", "division", "location_type", "urban", "garment", "remittance", "agri", "university"]

DEMO_PASSWORDS = {"admin": "admin123"}   # agents: password = "agent" + lowercase id, e.g. agenta01


def agent_password(agent_id: str) -> str:
    return f"agent{agent_id.lower()}"


def is_seeded() -> bool:
    with engine.connect() as c:
        try:
            return (c.execute(text("select count(*) from daily")).scalar() or 0) > 0
        except Exception:
            return False


def seed(force: bool = False, csv_path=None) -> dict:
    if not force and is_seeded():
        return {"seeded": False}
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    df = pd.read_csv(csv_path or settings.DATA_CSV, parse_dates=["date"]).sort_values(["agent_id", "date"])
    df["date"] = df["date"].dt.strftime("%Y-%m-%d")

    agents = df.drop_duplicates("agent_id")[AGENT_COLS + ["agent_capacity_cash", "agent_capacity_efloat"]].rename(
        columns={"agent_capacity_cash": "capacity_cash", "agent_capacity_efloat": "capacity_efloat"})
    agents.to_sql("agents", engine, if_exists="append", index=False)
    df[DAILY_COLS].to_sql("daily", engine, if_exists="append", index=False)
    df[TRUTH_COLS].to_sql("ground_truth", engine, if_exists="append", index=False)

    rows = []
    for r in df[["agent_id", "date", "closing_cash", "reported_cash", "report_missing"]].itertuples(index=False):
        rep = None if (r.report_missing == 1 or pd.isna(r.reported_cash)) else float(r.reported_cash)
        rc = reconcile(float(r.closing_cash), rep, DEFAULT_RULES["recon_tolerance"])
        rows.append(dict(agent_id=r.agent_id, date=r.date, reported_cash=rep, ledger_cash=float(r.closing_cash),
                         gap=rc["gap"], gap_pct=rc["gap_pct"], status=rc["status"], source="replay", submitted_at=None))
    pd.DataFrame(rows).to_sql("reports", engine, if_exists="append", index=False)

    now = datetime.now(timezone.utc).isoformat(timespec="seconds")
    with SessionLocal() as db:
        db.add(ConfigRow(key="sim_date", value=json.dumps(settings.SIM_DEFAULT_DATE)))
        for k, v in DEFAULT_RULES.items():
            db.add(ConfigRow(key=k, value=json.dumps(v)))
        db.add(User(username="admin", password_hash=hash_password(DEMO_PASSWORDS["admin"]), role="admin",
                    agent_id=None, display_name="Distribution Office"))
        for aid in sorted(agents["agent_id"]):
            db.add(User(username=aid.lower(), password_hash=hash_password(agent_password(aid)), role="agent",
                        agent_id=aid, display_name=f"Agent {aid}"))
        db.commit()
        from .models import AuditLog
        db.add(AuditLog(ts=now, actor="system", action="seed", entity="database", entity_id=None,
                        detail=json.dumps({"rows": int(len(df)), "agents": int(len(agents))})))
        db.commit()
    return {"seeded": True, "rows": int(len(df)), "agents": int(len(agents))}
