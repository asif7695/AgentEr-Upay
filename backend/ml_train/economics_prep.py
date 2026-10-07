"""Stage `economics`: pre-compute everything about the policy replay that does NOT depend on a cost assumption.

1. The model's required holding level on a coverage grid for every agent-day (one Monte Carlo run each, via the supplied
   engine's `extra_coverage`; level at buffer b is level(b0) + (b - b0) * capacity because the buffer enters linearly).
2. A replay of every policy configuration (habit / hybrid / model-only x coverage x safety buffer x order-up-to).

The app turns the per-agent outcomes into money live (trip cost, margin, customer multiplier), so changing an assumption
re-optimises instantly. No ground truth is used: demand on stock-out days is imputed from the model.
"""
from __future__ import annotations

import json
import pickle
import time
from pathlib import Path

import numpy as np
import pandas as pd

from app.ml import liquidity_forecaster as lf
from app.ml.dependence import CopulaRNG, load_dependence
from ml_train import conformal, replay
from ml_train.data import load

OUT = Path(__file__).resolve().parent / "out"
DATA = Path(__file__).resolve().parents[1] / "app" / "data"
COVS = (0.50, 0.60, 0.70, 0.80, 0.85, 0.90, 0.925, 0.95, 0.97, 0.99, 0.995)
BUFFERS = (0.05, 0.10, 0.15, 0.20)
UPS = (1.0, 1.25, 1.5, 2.0, 3.0)
REPLAY_START, REPLAY_END = "2025-09-01", "2025-12-24"        # the notebook's policy-replay window (115 days)


def prepare():
    t0 = time.time()
    df, F = load()
    lgbm = pickle.load(open(OUT / "lgbm_fitted.pkl", "rb"))
    main = json.loads((OUT / "main.json").read_text(encoding="utf-8"))
    Q0 = lgbm.predict(F)
    types_arr = F.location_type.to_numpy()
    Q = {f: conformal.apply(Q0[f], F[f"{f}_scale"].to_numpy(), main["conformal"][f], types_arr) for f in Q0}
    agents = sorted(df.agent_id.unique())
    typ = df.drop_duplicates("agent_id").set_index("agent_id")["location_type"]
    dates = pd.date_range(REPLAY_START, REPLAY_END)
    D, A = len(dates), len(agents)
    cfg = {**lf.DEFAULT_RISK_CONFIG}
    b0 = cfg["buffer_frac"]

    # ---- 1. required levels on the coverage grid
    req_c = np.zeros((len(COVS), D, A))
    req_e = np.zeros((len(COVS), D, A))
    sel = F[(F.origin_date >= REPLAY_START) & (F.origin_date <= REPLAY_END)]
    for (aid, od), g in sel.groupby(["agent_id", "origin_date"], sort=True):
        g = g.sort_values("h")
        if len(g) < lf.H:
            continue
        ix, r0 = g.index.to_numpy(), g.iloc[0]
        dep = load_dependence("t_copula", typ[aid])
        rng = CopulaRNG(int(aid[1:]) * 1_000_003 + pd.Timestamp(od).toordinal(), dep[0], cfg["n_paths"], dep[1])
        out = lf.risk_summary(Q["co"][ix], Q["ci"][ix], lf.QUANTILES, r0.cash0, r0.ef0, r0.cap_cash, r0.cap_ef,
                              int(r0.closed_ahead_origin), r0.co_scale, r0.ci_scale, cfg, rng, extra_coverage=COVS)
        di, ai = dates.get_loc(pd.Timestamp(od)), agents.index(aid)
        for k, pc in enumerate(COVS):
            req_c[k, di, ai], req_e[k, di, ai] = out["req_by_coverage"][pc]
    print(f"required levels: {time.time()-t0:.0f}s")

    # ---- 2. demand series, capacities, starting balances, working days (safe columns only)
    co = np.zeros((D, A)); ci = np.zeros((D, A)); cap_c = np.zeros(A); cap_e = np.zeros(A); cash0 = np.zeros(A); ef0 = np.zeros(A)
    imputed_days = 0
    for ai, aid in enumerate(agents):
        g = df[df.agent_id == aid].set_index("date")
        seg = g.loc[dates]
        rows = F.index[(F.agent_id == aid) & (F.h == 1)]
        order = F.loc[rows, "target_date"].to_numpy()
        lookup = dict(zip(order, rows))
        p = np.array([lookup[d] for d in dates.to_numpy()])
        q75_co, q75_ci = Q["co"][p, 3], Q["ci"][p, 3]
        so_c, so_e = (seg["cash_stockout"] == 1).to_numpy(), (seg["efloat_stockout"] == 1).to_numpy()
        co[:, ai] = np.where(so_c, np.maximum(seg["observed_cashout"].to_numpy(), q75_co), seg["observed_cashout"].to_numpy())
        ci[:, ai] = np.where(so_e, np.maximum(seg["observed_cashin"].to_numpy(), q75_ci), seg["observed_cashin"].to_numpy())
        imputed_days += int(so_c.sum() + so_e.sum())
        cap_c[ai], cap_e[ai] = seg["agent_capacity_cash"].iloc[0], seg["agent_capacity_efloat"].iloc[0]
        prev = g.loc[pd.Timestamp(REPLAY_START) - pd.Timedelta(days=1)]
        cash0[ai], ef0[ai] = prev["closing_cash"], prev["closing_efloat"]
    cal = df[df.agent_id == agents[0]].set_index("date")["is_working_day"]
    working = (cal.loc[pd.Timestamp(REPLAY_START):pd.Timestamp("2025-12-31")] == 1).to_numpy()
    print(f"demand series ready ({imputed_days} stock-out days imputed): {time.time()-t0:.0f}s")

    # ---- 3. replay every configuration
    def per_agent(res):
        return {k: np.round(v, 2).tolist() for k, v in res.items()}
    configs = []
    base = dict(co=co, ci=ci, working=working, cap_c=cap_c, cap_e=cap_e, cash0=cash0, ef0=ef0)
    # calibrate how often an agent notices a low balance so the habit baseline reproduces the stock-out days RECORDED in the ledger
    win = df[(df.date >= REPLAY_START) & (df.date <= REPLAY_END)]
    target_so = int(((win.cash_stockout == 1) | (win.efloat_stockout == 1)).sum())
    target_orders = int((win.cash_topup > 0).sum() + (win.efloat_topup > 0).sum())
    notice = np.random.default_rng(7).random((D, A))
    best = None
    for q in np.round(np.arange(0.05, 1.0001, 0.05), 2):
        r = replay.simulate("habit", notice=notice, q=q, **base)
        gap = abs(float(r["stockout_days"].sum()) - target_so)
        if best is None or gap < best[0]:
            best = (gap, float(q), float(r["stockout_days"].sum()), float(r["orders"].sum()))
    q_notice = best[1]
    print(f"calibration: ledger shows {target_so} stock-out days and {target_orders} orders; habit with notice prob {q_notice} gives {best[2]:.0f} / {best[3]:.0f}")
    base["notice"], base["q"] = notice, q_notice
    configs.append(dict(policy="habit", coverage=None, buffer=None, up=None, **per_agent(replay.simulate("habit", **base))))
    for k, pc in enumerate(COVS):
        for b in BUFFERS:
            for u in UPS:
                r = replay.simulate("hybrid", req_c=req_c[k], req_e=req_e[k], b0=b0, p_b=b, u=u, **base)
                configs.append(dict(policy="hybrid", coverage=pc, buffer=b, up=u, **per_agent(r)))
        r = replay.simulate("model_only", req_c=req_c[k], req_e=req_e[k], b0=b0, p_b=0.10, u=1.0, **base)
        configs.append(dict(policy="model_only", coverage=pc, buffer=0.10, up=1.0, **per_agent(r)))
    habit = configs[0]
    hy95 = next(c for c in configs if c["policy"] == "hybrid" and c["coverage"] == 0.95 and c["buffer"] == 0.10 and c["up"] == 1.0)
    mo95 = next(c for c in configs if c["policy"] == "model_only" and c["coverage"] == 0.95)
    tot = lambda c, k: float(np.sum(c[k]))
    print(f"replay done {time.time()-t0:.0f}s | habit stockout days {tot(habit,'stockout_days'):.0f} orders {tot(habit,'orders'):.0f} unserved {tot(habit,'unserved'):,.0f}")
    print(f"hybrid95 stockout days {tot(hy95,'stockout_days'):.0f} orders {tot(hy95,'orders'):.0f} unserved {tot(hy95,'unserved'):,.0f}")
    print(f"model_only95 stockout days {tot(mo95,'stockout_days'):.0f} orders {tot(mo95,'orders'):.0f} unserved {tot(mo95,'unserved'):,.0f}")
    out = dict(
        stamp="Synthetic data. Replay of 16 agents, 1 Sep to 24 Dec 2025. Demand on stock-out days imputed from the model (no ground truth).",
        period=dict(start=REPLAY_START, end=REPLAY_END, days=D), agents=agents, tiers={a: typ[a] for a in agents},
        capacity_cash=cap_c.round(0).tolist(), capacity_efloat=cap_e.round(0).tolist(),
        grid=dict(coverage=list(COVS), buffer=list(BUFFERS), up=list(UPS)), configs=configs,
        calibration=dict(notice_probability=q_notice, ledger_stockout_days=target_so, ledger_orders=target_orders,
                         note="how often an agent notices a low balance, fitted so the habit baseline reproduces the stock-out days in the ledger (safe columns only)"),
        notebook_reference=dict(habit=dict(stockout_days=64, orders=309, unserved=653720), hybrid95=dict(stockout_days=29, orders=503, unserved=232643),
                                note="the notebook replay used hidden true demand; this one imputes it from the model"),
    )
    (DATA / "policy_outcomes.json").write_text(json.dumps(out, separators=(",", ":")), encoding="utf-8")
    print(f"written {(DATA / 'policy_outcomes.json').stat().st_size // 1024} KB, {len(configs)} configs, {time.time()-t0:.0f}s")


if __name__ == "__main__":
    prepare()
