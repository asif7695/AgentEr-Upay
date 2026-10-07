"""SQLite schema. Dates are stored as ISO text (YYYY-MM-DD).

`daily` holds ONLY the safe ledger columns. Ground-truth demand lives in the isolated `ground_truth`
table which is read by exactly one service (services/reveal.py). Generator internals are never loaded.
"""
from sqlalchemy import Boolean, Column, Float, Integer, String, Text, UniqueConstraint, Index

from .db import Base


class Agent(Base):
    __tablename__ = "agents"
    agent_id = Column(String(8), primary_key=True)
    division = Column(String(32), nullable=False)
    location_type = Column(String(32), nullable=False)
    urban = Column(Integer, nullable=False)
    garment = Column(Integer, nullable=False)
    remittance = Column(Integer, nullable=False)
    agri = Column(Integer, nullable=False)
    university = Column(Integer, nullable=False)
    capacity_cash = Column(Float, nullable=False)
    capacity_efloat = Column(Float, nullable=False)


class Daily(Base):
    __tablename__ = "daily"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(8), nullable=False)
    date = Column(String(10), nullable=False)
    observed_cashout = Column(Float, nullable=False)
    observed_cashin = Column(Float, nullable=False)
    opening_cash = Column(Float, nullable=False)
    closing_cash = Column(Float, nullable=False)
    opening_efloat = Column(Float, nullable=False)
    closing_efloat = Column(Float, nullable=False)
    cash_topup = Column(Float, nullable=False)
    efloat_topup = Column(Float, nullable=False)
    cash_stockout = Column(Integer, nullable=False)
    efloat_stockout = Column(Integer, nullable=False)
    __table_args__ = (UniqueConstraint("agent_id", "date"), Index("ix_daily_agent_date", "agent_id", "date"))


class GroundTruth(Base):
    """SYNTHETIC GROUND TRUTH. Never exposed outside the admin 'Demo reveal' endpoint."""
    __tablename__ = "ground_truth"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(8), nullable=False)
    date = Column(String(10), nullable=False)
    true_cashout_demand = Column(Float, nullable=False)
    true_cashin_demand = Column(Float, nullable=False)
    unserved_cashout = Column(Float, nullable=False)
    unserved_cashin = Column(Float, nullable=False)
    __table_args__ = (UniqueConstraint("agent_id", "date"),)


class Report(Base):
    """Daily physical-cash self-report vs the ledger-implied cash."""
    __tablename__ = "reports"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(8), nullable=False)
    date = Column(String(10), nullable=False)
    reported_cash = Column(Float, nullable=True)       # null = no report
    ledger_cash = Column(Float, nullable=False)
    gap = Column(Float, nullable=True)
    gap_pct = Column(Float, nullable=True)
    status = Column(String(24), nullable=False)        # confirmed | needs_verification | missing
    source = Column(String(12), nullable=False)        # replay | agent
    submitted_at = Column(String(32), nullable=True)
    __table_args__ = (UniqueConstraint("agent_id", "date"),)


class Event(Base):
    """Human override: area event with a demand multiplier. NOT learned by the model."""
    __tablename__ = "events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String(12), nullable=False)         # all | division | agent
    target = Column(String(32), nullable=True)
    kind = Column(String(16), nullable=False)          # fair | road_closure | flood | other
    flow = Column(String(8), nullable=False, default="both")   # both | cashout | cashin
    multiplier = Column(Float, nullable=False)
    start_date = Column(String(10), nullable=False)
    end_date = Column(String(10), nullable=False)
    note = Column(String(200), nullable=True)
    active = Column(Boolean, nullable=False, default=True)
    created_by = Column(String(32), nullable=False)
    created_at = Column(String(32), nullable=False)


class Alert(Base):
    __tablename__ = "alerts"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(8), nullable=False)
    date = Column(String(10), nullable=False)
    type = Column(String(24), nullable=False)          # risk_high | risk_watch | report_missing | report_gap | capital
    severity = Column(String(8), nullable=False)       # high | watch | info
    message = Column(String(300), nullable=False)
    params = Column(Text, nullable=False, default="{}")
    status = Column(String(8), nullable=False, default="open")   # open | acked
    created_at = Column(String(32), nullable=False)
    acked_by = Column(String(32), nullable=True)
    acked_at = Column(String(32), nullable=True)
    __table_args__ = (UniqueConstraint("agent_id", "date", "type"),)


class Order(Base):
    """A planned top-up. `cash` = convert e-float to cash; `efloat` = buy e-float with cash."""
    __tablename__ = "orders"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(8), nullable=False)
    plan_date = Column(String(10), nullable=False)     # sim date the order was raised on
    due_date = Column(String(10), nullable=False)
    kind = Column(String(8), nullable=False)           # cash | efloat
    amount = Column(Float, nullable=False)
    order_type = Column(String(10), nullable=False)    # planned | emergency
    status = Column(String(12), nullable=False)        # proposed | acknowledged | scheduled | done | cancelled
    scheduled_for = Column(String(10), nullable=True)
    note = Column(String(200), nullable=True)
    created_by = Column(String(32), nullable=False)
    created_at = Column(String(32), nullable=False)
    updated_at = Column(String(32), nullable=False)


class ConfigRow(Base):
    __tablename__ = "config"
    key = Column(String(48), primary_key=True)
    value = Column(Text, nullable=False)               # JSON


class AuditLog(Base):
    __tablename__ = "audit_log"
    id = Column(Integer, primary_key=True, autoincrement=True)
    ts = Column(String(32), nullable=False)
    actor = Column(String(32), nullable=False)
    action = Column(String(32), nullable=False)
    entity = Column(String(24), nullable=False)
    entity_id = Column(String(32), nullable=True)
    detail = Column(Text, nullable=False, default="{}")


class User(Base):
    """Mock users only: 1 admin + 16 agents. No PII."""
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, autoincrement=True)
    username = Column(String(32), unique=True, nullable=False)
    password_hash = Column(String(80), nullable=False)
    role = Column(String(8), nullable=False)           # admin | agent
    agent_id = Column(String(8), nullable=True)
    display_name = Column(String(40), nullable=False)


class AdaptiveChange(Base):
    """A proposed (or auto-applied) per-agent adaptation of coverage / buffer / alert thresholds, with the evidence that justifies it."""
    __tablename__ = "adaptive_changes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    agent_id = Column(String(8), nullable=False)
    created_date = Column(String(10), nullable=False)  # sim date the evidence was cut at
    params = Column(Text, nullable=False)              # JSON {param: {from, to, prev, new}}
    reasons = Column(Text, nullable=False)             # JSON [{code, params, text}]
    profile = Column(Text, nullable=False)             # JSON snapshot of the behaviour profile
    status = Column(String(12), nullable=False)        # proposed | applied | dismissed | reverted | superseded
    mode = Column(String(8), nullable=False)           # suggest | auto
    decided_by = Column(String(32), nullable=True)
    decided_at = Column(String(32), nullable=True)
    created_at = Column(String(32), nullable=False)
    __table_args__ = (Index("ix_adaptive_agent", "agent_id", "status"),)


class DetectedEvent(Base):
    """An unusual-demand episode found by the detector (jump or sustained shift, agent or area). It only becomes a live demand
    multiplier (an `events` row) when an admin accepts it, or automatically in auto mode for small, bounded adjustments."""
    __tablename__ = "detected_events"
    id = Column(Integer, primary_key=True, autoincrement=True)
    scope = Column(String(12), nullable=False)         # agent | division
    target = Column(String(32), nullable=False)
    flow = Column(String(8), nullable=False)           # both | cashout | cashin
    kind = Column(String(8), nullable=False)           # jump | shift
    direction = Column(String(5), nullable=False)      # up | down
    multiplier = Column(Float, nullable=False)
    start_date = Column(String(10), nullable=False)    # first forecast day the multiplier would apply to
    end_date = Column(String(10), nullable=False)
    evidence = Column(Text, nullable=False)            # JSON: per-agent detections, z-scores, CUSUM, ratios
    status = Column(String(12), nullable=False)        # proposed | accepted | dismissed | expired | revoked
    event_id = Column(Integer, nullable=True)
    created_date = Column(String(10), nullable=False)
    decided_by = Column(String(32), nullable=True)
    decided_at = Column(String(32), nullable=True)
    created_at = Column(String(32), nullable=False)
