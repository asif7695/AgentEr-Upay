"""Adaptive decision intelligence, slice 1: agent behaviour profiles -> bounded, explainable per-agent adaptations.

Every number here is computed ONLY from ledger rows on or before the simulation date (no ground truth, no future rows):
  * model calibration  : the model's one-day-ahead quantiles at past origins versus what the ledger then recorded
                         (days on which the agent ran out are censored and skipped)
  * volatility, trend  : coefficient of variation and 14-day trend of cash-out
  * alert track record : the status the model WOULD have shown at each past origin (reduced Monte Carlo) versus whether
                         the agent actually ran out inside that window; this reflects the agent's own replenishment habits
  * report reliability : share of confirmed cash reports over 30 days
The rules in rules/adaptive_rules.py turn a profile into small, gated, bounded changes. In `suggest` mode an admin approves
each change; in `auto` mode it is applied at once within the same guard rails; both are audit-logged and reversible.
"""
from __future__ import annotations

import json
import threading
from collections import OrderedDict
from datetime import date, timedelta

import numpy as np
import pandas as pd
from sqlalchemy import select

from ..errors import ApiError
from ..ml import conformal
from ..ml import liquidity_forecaster as lf
from ..ml import serving
from ..ml.dependence import CopulaRNG, load_dependence
from ..ml.model_store import effective_model, get_bundle
from ..models import AdaptiveChange, Report
from ..rules import adaptive_rules as ar
from ..rules import business_rules as br
from .context import Ctx, audit, ledger, now_iso, set_config

N_ORIGINS = 45            # past forecast origins examined
MC_PATHS = 500            # reduced Monte Carlo for historic risk (the live forecast uses the full number)
HIST_DAYS = 120
_lock = threading.Lock()
_profiles: "OrderedDict[tuple, dict]" = OrderedDict()
_risks: dict[tuple, tuple[float, float, int]] = {}


_origins: dict[tuple, tuple] = {}


def invalidate(agent_id: str | None = None, from_date: date | None = None) -> None:
    """Forget cached per-origin work (used when the ledger is replaced, e.g. by the shock-injection evaluation)."""
    with _lock:
        _profiles.clear()
        for store in (_origins, _risks):
            for k in [k for k in store if (agent_id is None or k[1] == agent_id) and (from_date is None or k[2] >= pd.Timestamp(from_date) - timedelta(days=lf.H))]:
                del store[k]


def _fill(model: str, d: date) -> None:
    """Computes the missing past origins for ALL agents in one vectorised pass (one calendar, one set of LightGBM calls).
    Features and quantiles at an origin only use data up to that origin, so each (agent, origin) is computed once and kept."""
    d_ts = pd.Timestamp(d)
    origins = [d_ts - timedelta(k) for k in range(1, N_ORIGINS + 1)]
    todo = {aid: [o for o in origins if (model, aid, o) not in _origins] for aid in ledger.agents}
    todo = {aid: miss for aid, miss in todo.items() if miss}
    if not todo:
        return
    need = sorted({o for miss in todo.values() for o in miss})
    bundle = get_bundle(model)
    parts, first_dates = [], None
    for aid in sorted(todo):
        g = ledger.frames[aid]
        hist = g[g["date"] <= d_ts].tail(HIST_DAYS)
        if len(hist) < lf.MIN_HIST + 2:
            continue
        if first_dates is None:
            first_dates = list(hist["date"]) + [d_ts + timedelta(i) for i in range(1, lf.H + 1)]
            cal = lf.build_calendar(first_dates + [d_ts + timedelta(lf.H + 30)], bundle["calendar_config"]).iloc[:len(first_dates)].reset_index(drop=True)
        elif len(hist) != len(first_dates) - lf.H:
            continue                  # agents share one date axis in this dataset; anything else is skipped rather than guessed
        row = serving.agent_row_for_serving(bundle, aid)
        df = cal.copy()
        df["agent_id"] = aid
        for c in lf.TRAIT_COLS:
            df[c] = row[c]
        df["agent_capacity_cash"], df["agent_capacity_efloat"] = row["capacity_cash"], row["capacity_efloat"]
        pad = [np.nan] * lf.H
        for col in ("observed_cashout", "observed_cashin", "closing_cash", "closing_efloat"):
            df[col] = list(hist[col]) + pad
        parts.append(df)
    if not parts:
        return
    f = lf.make_features(pd.concat(parts, ignore_index=True), origins=need)
    if f.empty:
        return
    f = f.sort_values(["agent_id", "origin_date", "h"]).reset_index(drop=True)
    q = lf.predict_quantiles(bundle, f)
    qco, qci = q["co"], q["ci"]
    calib = bundle.get("calibration")
    if calib:
        types = f["agent_id"].map({a: v["location_type"] for a, v in ledger.agents.items()}).to_numpy()
        qco = conformal.apply(qco, f["co_scale"].to_numpy(), calib["co"], types)
        qci = conformal.apply(qci, f["ci_scale"].to_numpy(), calib["ci"], types)
    for (aid, od), idx in f.groupby(["agent_id", "origin_date"]).indices.items():
        if len(idx) == lf.H:
            _origins[(model, aid, pd.Timestamp(od))] = (f.iloc[idx].reset_index(drop=True), qco[idx], qci[idx])


def _origin_rows(model: str, agent_id: str, d: date) -> list[tuple]:
    """(origin, features h=1..7, calibrated cash-out quantiles, cash-in quantiles) for the last N_ORIGINS origins before d."""
    _fill(model, d)
    d_ts = pd.Timestamp(d)
    keys = [d_ts - timedelta(k) for k in range(N_ORIGINS, 0, -1)]
    return [(o, *_origins[(model, agent_id, o)]) for o in keys if (model, agent_id, o) in _origins]


def _past_risk(model: str, agent_id: str, origin: pd.Timestamp, g7: pd.DataFrame, qco: np.ndarray, qci: np.ndarray, buffer_frac: float,
               tier: str) -> tuple[float, float, int]:
    key = (model, agent_id, origin, round(buffer_frac, 3))
    hit = _risks.get(key)
    if hit is not None:
        return hit
    bundle = get_bundle(model)
    r0 = g7.iloc[0]
    cfg = {**bundle["risk_config"], "buffer_frac": buffer_frac, "n_paths": MC_PATHS}
    dep = load_dependence("t_copula", tier)
    seed = int(agent_id[1:]) * 1_000_003 + origin.toordinal()
    rng = np.random.default_rng(seed) if dep is None else CopulaRNG(seed, dep[0], MC_PATHS, dep[1])
    out = lf.risk_summary(qco, qci, bundle["quantiles"], float(r0["cash0"]), float(r0["ef0"]), float(r0["cap_cash"]), float(r0["cap_ef"]),
                          int(r0["closed_ahead_origin"]), r0["co_scale"], r0["ci_scale"], cfg, rng)
    W = int(out["coverage_window_days"])
    res = (float(out["cash_risk_pct_by_day"][W - 1]), float(out["efloat_risk_pct_by_day"][W - 1]), W)
    _risks[key] = res
    return res


def _rules_for_profile(ctx: Ctx) -> dict:
    """Rules WITHOUT per-agent overrides: the profile must not feed back on settings it has itself produced."""
    return {**ctx.rules, "agent_overrides": {}}


def agent_profile(ctx: Ctx, agent_id: str, d: date) -> dict:
    model = effective_model(ctx.rules["model_choice"])
    rules = _rules_for_profile(ctx)
    agent = ctx.agent(agent_id)
    tier = agent["location_type"]
    high, watch = rules["high_threshold"], rules["watch_threshold"]
    buf = br.risk_cfg_overrides(rules, tier)["buffer_frac"]
    key = (model, agent_id, d.isoformat(), round(buf, 3), high, watch)
    with _lock:
        if key in _profiles:
            _profiles.move_to_end(key)
            return _profiles[key]

    g = ledger.frames[agent_id]
    gd = g[g["date"] <= pd.Timestamp(d)].reset_index(drop=True)
    flags = gd.set_index("date")[["cash_stockout", "efloat_stockout"]]
    prof = dict(agent_id=agent_id, tier=tier, as_of=d.isoformat(), history_days=int(len(gd)), n_days=0, n_obs=0, breaches=0, breach_rate=None, z=None,
                hit80=None, bias_pct=None, vol=None, trend_pct=None, stockout_days_60=int(((gd.tail(60)["cash_stockout"] + gd.tail(60)["efloat_stockout"]) > 0).sum()),
                alert_n=0, alert_hits=0, precision=None, report_reliability=None)

    # volatility and trend of cash-out
    co = gd["observed_cashout"].tail(28)
    if len(co) >= 14 and co.mean() > 0:
        prof["vol"] = float(co.std(ddof=1) / co.mean())
    if len(gd) >= 28:
        a, b = gd["observed_cashout"].tail(14).mean(), gd["observed_cashout"].iloc[-28:-14].mean()
        prof["trend_pct"] = float(100 * (a / b - 1)) if b > 0 else None

    rows = _origin_rows(model, agent_id, d)
    if rows:
        n_days = n_obs = breaches = inside = 0
        ratios: list[float] = []
        alerts = hits = 0
        for od, f7, qco, qci in rows:
            t = od + timedelta(days=1)                    # the day this origin's one-day-ahead forecast was about (<= d)
            if (pd.Timestamp(d) - t).days < 28:
                fl = flags.loc[t]
                r1 = f7.iloc[0]
                seen = False
                for flow, q, yv, so in (("co", qco[0], r1["y_co"], fl["cash_stockout"]), ("ci", qci[0], r1["y_ci"], fl["efloat_stockout"])):
                    if so or not np.isfinite(yv):
                        continue          # censored: the observed value is not the demand
                    seen = True
                    n_obs += 1
                    breaches += int(yv > q[4])
                    inside += int(q[0] <= yv <= q[4])
                    if flow == "co" and q[2] > 0:
                        ratios.append(yv / q[2])
                n_days += int(seen)
            # alert track record: the status the model would have shown at this origin vs a real stock-out inside that window
            cr, er, W = _past_risk(model, agent_id, od, f7, qco, qci, buf, tier)
            if od + timedelta(days=W) > pd.Timestamp(d):
                continue          # the window has not closed yet: outcome unknown
            win = flags.loc[od + timedelta(days=1): od + timedelta(days=W)]
            for risk, col in ((cr, "cash_stockout"), (er, "efloat_stockout")):
                if risk >= watch:
                    alerts += 1
                    hits += int(win[col].max() > 0) if len(win) else 0
        prof.update(n_days=n_days, n_obs=n_obs, breaches=breaches, alert_n=alerts, alert_hits=hits,
                    precision=hits / alerts if alerts else None)
        if n_obs:
            prof["breach_rate"] = breaches / n_obs
            prof["z"] = ar.breach_z(breaches / n_obs, n_obs)
            prof["hit80"] = inside / n_obs
        if ratios:
            prof["bias_pct"] = float(100 * (np.median(ratios) - 1))

    rep = list(ctx.db.scalars(select(Report.status).where(Report.agent_id == agent_id, Report.date <= d.isoformat(),
                                                           Report.date > (d - timedelta(days=30)).isoformat())))
    if rep:
        prof["report_reliability"] = sum(s == "confirmed" for s in rep) / len(rep)
    with _lock:
        _profiles[key] = prof
        while len(_profiles) > 600:
            _profiles.popitem(last=False)
    return prof


def network_profiles(ctx: Ctx, d: date) -> tuple[list[dict], dict]:
    profs = [agent_profile(ctx, aid, d) for aid in sorted(ledger.agents)]
    tiers = {aid: a["location_type"] for aid, a in ledger.agents.items()}
    return profs, ar.network_context(profs, tiers)


def _base_for(rules: dict, agent_id: str) -> dict:
    tier = ledger.agents[agent_id]["location_type"]
    cfg = br.risk_cfg_overrides({**rules, "agent_overrides": {}}, tier)
    return dict(coverage_prob=cfg["coverage_prob"], buffer_frac=cfg["buffer_frac"], high_threshold=rules["high_threshold"], watch_threshold=rules["watch_threshold"])


def _desired(rules: dict, profile: dict, net: dict) -> dict:
    return ar.propose(profile, _base_for(rules, profile["agent_id"]), net)


# ------------------------------------------------------------------ changes ---
def change_dict(c: AdaptiveChange) -> dict:
    return dict(id=c.id, agent_id=c.agent_id, created_date=c.created_date, params=json.loads(c.params), reasons=json.loads(c.reasons),
                profile=json.loads(c.profile), status=c.status, mode=c.mode, decided_by=c.decided_by, decided_at=c.decided_at, created_at=c.created_at)


def _set_overrides(ctx: Ctx, overrides: dict) -> None:
    merged = br.validate_rules({"agent_overrides": overrides}, ctx.rules)
    set_config(ctx.db, "agent_overrides", merged["agent_overrides"])
    ctx.rules["agent_overrides"] = merged["agent_overrides"]


def _apply(ctx: Ctx, c: AdaptiveChange, actor: str) -> None:
    params = json.loads(c.params)
    ov = {a: dict(v) for a, v in ctx.rules["agent_overrides"].items()}
    cur = ov.setdefault(c.agent_id, {})
    for p, v in params.items():
        if v["new"] is None:
            cur.pop(p, None)
        else:
            cur[p] = v["new"]
    if not cur:
        ov.pop(c.agent_id, None)
    _set_overrides(ctx, ov)
    c.status, c.decided_by, c.decided_at = "applied", actor, now_iso()
    audit(ctx.db, actor, "adaptive_apply", "adaptive_change", c.id, dict(agent_id=c.agent_id, params=params, mode=c.mode))


def decide(ctx: Ctx, actor: str, change_id: int, action: str) -> dict:
    c = ctx.db.get(AdaptiveChange, change_id)
    if c is None:
        raise ApiError(404, "not_found", "Change not found")
    if action == "approve":
        if c.status != "proposed":
            raise ApiError(409, "invalid_transition", f"A {c.status} change cannot be approved")
        _apply(ctx, c, actor)
    elif action == "dismiss":
        if c.status != "proposed":
            raise ApiError(409, "invalid_transition", f"A {c.status} change cannot be dismissed")
        c.status, c.decided_by, c.decided_at = "dismissed", actor, now_iso()
        audit(ctx.db, actor, "adaptive_dismiss", "adaptive_change", c.id, dict(agent_id=c.agent_id))
    elif action == "revert":
        if c.status != "applied":
            raise ApiError(409, "invalid_transition", "Only an applied change can be reverted")
        params = json.loads(c.params)
        ov = {a: dict(v) for a, v in ctx.rules["agent_overrides"].items()}
        cur = ov.setdefault(c.agent_id, {})
        for p, v in params.items():
            if v["prev"] is None:
                cur.pop(p, None)
            else:
                cur[p] = v["prev"]
        if not cur:
            ov.pop(c.agent_id, None)
        _set_overrides(ctx, ov)
        c.status, c.decided_by, c.decided_at = "reverted", actor, now_iso()
        audit(ctx.db, actor, "adaptive_revert", "adaptive_change", c.id, dict(agent_id=c.agent_id, params=params))
    else:
        raise ApiError(422, "validation_error", "action must be approve, dismiss or revert")
    ctx.db.commit()
    return change_dict(c)


def run_nightly(ctx: Ctx, d: date, actor: str = "system") -> dict:
    """Evaluate every agent at date d; propose (suggest) or apply (auto) changes. Idempotent for a given date."""
    mode = ctx.rules["adaptive_mode"]
    if mode == "off":
        return dict(mode=mode, proposed=0, applied=0)
    profs, net = network_profiles(ctx, d)
    proposed = applied = 0
    for p in profs:
        aid = p["agent_id"]
        desired = _desired(ctx.rules, p, net)
        base = _base_for(ctx.rules, aid)
        active = ctx.rules["agent_overrides"].get(aid, {})
        # target state per parameter: desired value, or None (= no override, use the tier / global value)
        target = {k: desired["values"].get(k) for k in ar.PARAMS}
        diff = {k: dict(**{"from": active.get(k, base[k]), "to": target[k] if target[k] is not None else base[k], "prev": active.get(k), "new": target[k]})
                for k in ar.PARAMS if target[k] != active.get(k)}
        if not diff:
            continue
        last = ctx.db.scalar(select(AdaptiveChange).where(AdaptiveChange.agent_id == aid, AdaptiveChange.status.in_(("proposed", "applied")))
                             .order_by(AdaptiveChange.id.desc()).limit(1))
        pending = last if last is not None and last.status == "proposed" else None
        if last is not None and last.status == "applied" and (d - date.fromisoformat(last.created_date)).days < ar.GUARD["cooldown_days"]:
            continue          # cool-down: at most one applied change per agent per week
        if pending is not None:
            if {k: v["new"] for k, v in json.loads(pending.params).items()} == {k: v["new"] for k, v in diff.items()}:
                continue          # same proposal is already waiting for the admin
            pending.status = "superseded"
        reasons = desired["reasons"] or [dict(code="release", params={}, text="evidence no longer supports the adapted settings; return to the standard values")]
        c = AdaptiveChange(agent_id=aid, created_date=d.isoformat(), params=json.dumps(diff), reasons=json.dumps(reasons), profile=json.dumps(p),
                           status="proposed", mode=mode, created_at=now_iso())
        ctx.db.add(c)
        ctx.db.flush()
        audit(ctx.db, actor, "adaptive_propose", "adaptive_change", c.id, dict(agent_id=aid, params=diff, reasons=[r["text"] for r in reasons]))
        proposed += 1
        if mode == "auto":
            _apply(ctx, c, "system")
            applied += 1
    return dict(mode=mode, proposed=proposed, applied=applied)


def overview(ctx: Ctx, d: date) -> dict:
    ctx.check_date(d)
    profs, net = network_profiles(ctx, d)
    changes = [change_dict(c) for c in ctx.db.scalars(select(AdaptiveChange).order_by(AdaptiveChange.id.desc()).limit(200))]
    agents = []
    for p in profs:
        aid = p["agent_id"]
        base = _base_for(ctx.rules, aid)
        desired = _desired(ctx.rules, p, net)
        agents.append(dict(agent_id=aid, division=ledger.agents[aid]["division"], tier=p["tier"], profile=p, base=base,
                           active=ctx.rules["agent_overrides"].get(aid, {}), evidence_supports=desired["values"], reasons=desired["reasons"]))
    return dict(date=d.isoformat(), mode=ctx.rules["adaptive_mode"], guard=ar.GUARD, network=net, agents=agents, changes=changes,
                pending=sum(c["status"] == "proposed" for c in changes), active=sum(1 for v in ctx.rules["agent_overrides"].values() if v),
                note="Computed from ledger rows up to the simulation date only. Changes are recommendations until an admin approves them (suggest mode); every change is audit-logged and reversible.")
