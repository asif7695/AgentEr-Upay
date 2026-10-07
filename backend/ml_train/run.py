"""Orchestrates the model-development evidence. Stages write JSON to ml_train/out/, `assemble` builds the app files.

    python -m ml_train.run main        # compare model families on the untouched Sep-Dec test period, build challenger + CQR
    python -m ml_train.run unseen      # leave-agents-out CV and the Eid-ul-Adha hold-out
    python -m ml_train.run assemble    # -> backend/models/challenger_bundle.pkl, backend/app/data/model_evidence.json
Run from the backend folder.
"""
from __future__ import annotations

import json
import pickle
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import settings  # noqa: E402
from app.ml import liquidity_forecaster as lf  # noqa: E402
from app.ml.model_store import get_bundle  # noqa: E402
from ml_train import conformal, families as fam  # noqa: E402
from ml_train.data import SEED, load, masks, uncensored  # noqa: E402
from ml_train.metrics import evaluate_flow  # noqa: E402

OUT = Path(__file__).resolve().parent / "out"
MODELS_DIR = Path(__file__).resolve().parents[1] / "models"
OUT.mkdir(exist_ok=True)
MODELS_DIR.mkdir(exist_ok=True)


def _eval(pred: dict, F: pd.DataFrame, mask: pd.Series) -> dict:
    res = {}
    for flow in ("co", "ci"):
        keep = (mask & uncensored(F, flow)).to_numpy()
        res[flow] = evaluate_flow(pred[flow], F[f"{flow}_scale"].to_numpy(), F[f"y_{flow}"].to_numpy(), keep)
    return res


def _by_type(pred, F, mask):
    return {t: _eval({f: pred[f][(F.location_type == t).to_numpy()] for f in pred}, F[F.location_type == t], mask[F.location_type == t])
            for t in sorted(F.location_type.unique())}


def stage_main():
    t0 = time.time()
    df, F = load()
    M = masks(F)
    TE = M["TE"]
    print(f"features {len(F):,} rows | train {M['TR'].sum():,} val {M['VA'].sum():,} cal {M['CAL'].sum():,} test {TE.sum():,}")

    lgbm = fam.LightGBM().fit(F, M["TR"], M["VA"])
    print(f"lightgbm fitted {time.time()-t0:.0f}s, trees:", {f"{k[0]}{k[1]}": v for k, v in lgbm.info.items()})
    fitted = {"lightgbm": lgbm}
    for cls in (fam.LogNormalGBM, fam.Seasonal, fam.LinearQR):
        t1 = time.time()
        fitted[cls.name] = cls().fit(F, M["TR"], M["VA"])
        print(f"{cls.name} fitted {time.time()-t1:.0f}s")
    preds = {"supplied_bundle": fam.Supplied(get_bundle()).predict(F), "same_weekday_last_week": fam.SameWeekday().predict(F)}
    preds.update({"lightgbm_ours": lgbm.predict(F)})
    for n, m in fitted.items():
        if n != "lightgbm":
            preds[n] = m.predict(F)

    # conformal calibration of OUR lightgbm on the calibration month (never used for fitting)
    Q = preds["lightgbm_ours"]
    scale = {f: F[f"{f}_scale"].to_numpy() for f in ("co", "ci")}
    cal = M["CAL"].to_numpy()
    calib = conformal.fit({f: (Q[f] / scale[f][:, None])[cal] for f in Q}, {f: (F[f"y_{f}"].to_numpy() / scale[f])[cal] for f in Q},
                          {f: uncensored(F, f).to_numpy()[cal] for f in Q}, F.location_type.to_numpy()[cal])
    preds["lightgbm_ours_cqr"] = {f: conformal.apply(Q[f], scale[f], calib[f], F.location_type.to_numpy()) for f in Q}

    table = {n: _eval(p, F, TE) for n, p in preds.items()}
    cal_check = {n: _eval(p, F, M["CAL"]) for n, p in preds.items() if n.startswith("lightgbm_ours")}   # calibration window (in-sample for CQR)
    by_type = {n: _by_type(preds[n], F, TE) for n in ("supplied_bundle", "lightgbm_ours", "lightgbm_ours_cqr")}
    by_h = {n: {int(h): _eval({f: preds[n][f][(F.h == h).to_numpy()] for f in preds[n]}, F[F.h == h], TE[F.h == h]) for h in range(1, 8)}
            for n in ("lightgbm_ours", "lightgbm_ours_cqr")}
    out = dict(split=dict(train_target_end=SPLITS_END, val="2025-07", calibration="2025-08", test="2025-09-01 to 2025-12-31"),
               rows=dict(train=int(M["TR"].sum()), val=int(M["VA"].sum()), cal=int(M["CAL"].sum()), test=int(TE.sum())),
               table=table, calibration_window=cal_check, by_type=by_type, by_horizon=by_h, conformal=calib,
               trees={f"{k[0]}_{k[1]}": int(v) for k, v in lgbm.info.items()})
    (OUT / "main.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    with open(OUT / "lgbm_fitted.pkl", "wb") as fh:
        pickle.dump(lgbm, fh)
    print_table(table)
    print(f"done in {time.time()-t0:.0f}s")


SPLITS_END = "2025-06-30"


def stage_paths():
    """Estimate multi-day dependence on residuals of the calibrated challenger from Jul-Aug (not used to fit the model),
    then test simulated 3-/7-day tails out-of-sample on Sep-Dec for every dependence model."""
    from ml_train import paths
    t0 = time.time()
    df, F = load()
    M = masks(F)
    lgbm = pickle.load(open(OUT / "lgbm_fitted.pkl", "rb"))
    main = json.loads((OUT / "main.json").read_text(encoding="utf-8"))
    Q0 = lgbm.predict(F)
    types_arr = F.location_type.to_numpy()
    Q = {f: conformal.apply(Q0[f], F[f"{f}_scale"].to_numpy(), main["conformal"][f], types_arr) for f in Q0}
    types = F.drop_duplicates("agent_id").set_index("agent_id")["location_type"]
    est = paths.estimate(paths.residual_matrix(F, Q, M["VA"] | M["CAL"]), types)
    print(f"estimated on {est['n_origins']} origins (Jul-Aug): rho_day {est['rho_day']:.3f}, rho_cross {est['rho_cross']:.3f}")
    ev = paths.evaluate_tails(F, Q, M["TE"], est, types)
    for m in ev:
        if m.startswith("_"):
            continue
        print(f"{m:15s} 7d tail_error {ev[m]['7d']['tail_error']:.4f} cov_err {ev[m]['7d']['coverage_error']:.4f} | 3d tail_error {ev[m]['3d']['tail_error']:.4f}")
    # persist the estimate for the serving path (default t-copula nu from the evidence, lowest 7-day tail error among t variants)
    nus = {4: "t_copula_nu4", 6: "t_copula_nu6", 10: "t_copula_nu10"}
    best_nu = min(nus, key=lambda n: ev[nus[n]]["7d"]["tail_error"])
    corr_out = dict(
        order=["cashout_h1..h7", "cashin_h1..h7"],
        method="Dependence of the calibrated challenger's probability-integral-transform residuals (Gaussian / AR(1) / Student-t copula)",
        dataset="synthetic v2; Jul-Aug 2025 residuals (not used to fit the model); stock-out (censored) days excluded",
        n_origins=est["n_origins"], t_nu=best_nu, ar1=dict(rho_day=round(est["rho_day"], 4), rho_cross=round(est["rho_cross"], 4)),
        pooled=np.round(est["pooled"], 4).tolist(), by_type={t: np.round(m, 4).tolist() for t, m in est["by_type"].items()},
        mean_adjacent_day_corr=round(est["rho_day"], 3), mean_cross_flow_same_day_corr=round(est["rho_cross"], 3))
    (Path(__file__).resolve().parents[1] / "app" / "data" / "error_correlation.json").write_text(json.dumps(corr_out, indent=1), encoding="utf-8")
    (OUT / "paths.json").write_text(json.dumps(dict(
        protocol="Observed 3- and 7-day cumulative cash-out / net drain vs simulated quantiles, Sep-Dec 2025 (every 2nd origin, uncensored windows). "
                 "Lower error = closer to nominal.", estimate=dict(n_origins=est["n_origins"], rho_day=est["rho_day"], rho_cross=est["rho_cross"], t_nu=best_nu),
        results=ev), indent=1), encoding="utf-8")
    print(f"t nu={best_nu}; done {time.time()-t0:.0f}s")


def stage_assemble():
    """Challenger bundle (our boosters + conformal widths, same layout as the supplied bundle) + the evidence file for the app."""
    import copy
    from datetime import datetime, timezone
    main = json.loads((OUT / "main.json").read_text(encoding="utf-8"))
    unseen = json.loads((OUT / "unseen.json").read_text(encoding="utf-8"))
    lgbm = pickle.load(open(OUT / "lgbm_fitted.pkl", "rb"))
    base = copy.deepcopy(get_bundle())
    agents = base["agents"].drop(columns=[c for c in ("base_cashout", "base_cashin", "noise_std") if c in base["agents"].columns])
    bundle = {**lgbm.bundle(base), "agents": agents, "name": "agent-liquidity-challenger", "version": "2.0.0",
              "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
              "calibration": main["conformal"],
              "trained_on": dict(rows=main["rows"]["train"] + main["rows"]["val"], agents=16, targets="2025-01-29 to 2025-07-31 (fit), 2025-08 (calibration)",
                                 data="synthetic (generate_dataset_v2.py); safe ledger columns only, censoring-aware labels"),
              "eval_summary": main["table"]["lightgbm_ours_cqr"], "notes": "Retrained by ml_train/run.py; out-of-sample from 2025-09-01."}
    with open(MODELS_DIR / "challenger_bundle.pkl", "wb") as fh:
        pickle.dump(bundle, fh)
    corr_path = Path(__file__).resolve().parents[1] / "app" / "data" / "error_correlation.json"
    corr = json.loads(corr_path.read_text(encoding="utf-8")) if corr_path.exists() else {}
    extra = {}
    for nm in ("risk.json", "paths.json"):
        if (OUT / nm).exists():
            extra[nm[:-5]] = json.loads((OUT / nm).read_text(encoding="utf-8"))
    ev = dict(
        stamp="Synthetic data. Out-of-sample on a chronological split. NOT validated on real upay data.",
        generated=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        split=main["split"], rows=main["rows"], protocol=dict(
            labels="observed (censored) flows + stock-out flags; ground-truth columns are dropped before any feature is built",
            metrics="WAPE of P50, mean relative pinball loss over 5 quantiles, coverage of the P10-P90 (80%) and P25-P75 (50%) intervals, "
                    "all on uncensored days of the test period",
            caveat="The supplied bundle was trained on all of 2025, so its Sep-Dec numbers are in-sample; they are shown for reference, not as a fair comparison."),
        families=main["table"], by_type=main["by_type"], by_horizon=main["by_horizon"], conformal=main["conformal"],
        unseen_agents=unseen["unseen_agents"], unseen_agents_by_type=unseen["unseen_agents_cqr_by_type"], unseen_event=unseen["unseen_event"],
        dependence={k: v for k, v in corr.items() if k not in ("by_type",)}, **extra)
    (Path(__file__).resolve().parents[1] / "app" / "data" / "model_evidence.json").write_text(json.dumps(ev, indent=1), encoding="utf-8")
    print("challenger bundle:", (MODELS_DIR / "challenger_bundle.pkl").stat().st_size // 1024, "KB; evidence file written")


def _calibrated(Q, F, M, mask_train_agents=None):
    """CQR fitted on the calibration month (optionally only on the agents the model was trained on)."""
    scale = {f: F[f"{f}_scale"].to_numpy() for f in ("co", "ci")}
    cal = M["CAL"].to_numpy() & (np.ones(len(F), bool) if mask_train_agents is None else mask_train_agents)
    calib = conformal.fit({f: (Q[f] / scale[f][:, None])[cal] for f in Q}, {f: (F[f"y_{f}"].to_numpy() / scale[f])[cal] for f in Q},
                          {f: uncensored(F, f).to_numpy()[cal] for f in Q}, F.location_type.to_numpy()[cal])
    return {f: conformal.apply(Q[f], scale[f], calib[f], F.location_type.to_numpy()) for f in Q}


def stage_unseen():
    t0 = time.time()
    df, F = load()
    M = masks(F)
    TE = M["TE"]
    seen = pickle.load(open(OUT / "lgbm_fitted.pkl", "rb"))
    # ---- (1) unseen AGENTS: 4-fold leave-agents-out, folds spread across agent types
    order = F.drop_duplicates("agent_id").sort_values(["location_type", "agent_id"])["agent_id"].tolist()
    fold_of = {a: i % 4 for i, a in enumerate(order)}
    F["fold"] = F["agent_id"].map(fold_of)
    rows = {"lightgbm_ours": [], "lightgbm_ours_cqr": [], "lognormal_gbm": [], "seasonal_profile": []}
    P_all = {k: {"co": np.zeros((len(F), 5)), "ci": np.zeros((len(F), 5))} for k in rows}
    P_seen = seen.predict(F)
    for k in range(4):
        held = (F["fold"] == k).to_numpy()
        tr, va = M["TR"] & ~held, M["VA"] & ~held
        m1 = fam.LightGBM().fit(F, tr, va)
        Q1 = m1.predict(F)
        Q1c = _calibrated(Q1, F, M, ~held)
        Q2 = fam.LogNormalGBM().fit(F, tr, va).predict(F)
        Q3 = fam.Seasonal().fit(F, tr, va).predict(F)
        for name, Q in (("lightgbm_ours", Q1), ("lightgbm_ours_cqr", Q1c), ("lognormal_gbm", Q2), ("seasonal_profile", Q3)):
            for f in ("co", "ci"):
                P_all[name][f][held] = Q[f][held]
        print(f"fold {k} done ({time.time()-t0:.0f}s)")
    res = {name: _eval(P, F, TE) for name, P in P_all.items()}
    res["lightgbm_ours_agent_seen"] = _eval(P_seen, F, TE)
    res["same_weekday_last_week"] = _eval(fam.SameWeekday().predict(F), F, TE)
    by_type = {t: _eval({f: P_all["lightgbm_ours_cqr"][f][(F.location_type == t).to_numpy()] for f in ("co", "ci")}, F[F.location_type == t], TE[F.location_type == t])
               for t in sorted(F.location_type.unique())}
    # ---- (2) unseen EVENT: Eid-ul-Adha removed from training
    ad = M["ADHA"]
    tr, va = M["TR"] & ~ad, M["VA"]
    held_out = fam.LightGBM().fit(F, tr, va).predict(F)
    seas = fam.Seasonal().fit(F, tr, va).predict(F)
    ev = {"adha_held_out": _eval(held_out, F, ad), "adha_seen_in_training": _eval(seen.predict(F), F, ad),
          "seasonal_profile_adha_held_out": _eval(seas, F, ad), "same_weekday_last_week": _eval(fam.SameWeekday().predict(F), F, ad)}
    out = dict(folds={a: int(f) for a, f in fold_of.items()}, unseen_agents=res, unseen_agents_cqr_by_type=by_type, unseen_event=ev,
               note="Unseen agents: 4-fold leave-agents-out on the Sep-Dec test period. Unseen event: Eid-ul-Adha (19 May-20 Jun) removed from training.")
    (OUT / "unseen.json").write_text(json.dumps(out, indent=1), encoding="utf-8")
    for k, v in res.items():
        print(f"{k:28s} co WAPE {v['co']['wape']:.3f} cov80 {v['co']['coverage80']:.3f} | ci WAPE {v['ci']['wape']:.3f} cov80 {v['ci']['coverage80']:.3f}")
    for k, v in ev.items():
        print(f"ADHA {k:34s} co {v['co']['wape']:.3f} ci {v['ci']['wape']:.3f}")
    print(f"done {time.time()-t0:.0f}s")


def print_table(table):
    for flow in ("co", "ci"):
        print(f"\n== {flow} (Sep-Dec test, uncensored days) ==")
        print(f"{'model':28s} {'WAPE':>6s} {'pinball':>8s} {'cov80':>6s} {'cov50':>6s} {'width80':>8s}")
        for n, r in table.items():
            x = r[flow]
            print(f"{n:28s} {x['wape']:6.3f} {x['pinball']:8.4f} {x['coverage80']:6.3f} {x['coverage50']:6.3f} {x['width80']:8.3f}")


if __name__ == "__main__":
    {"main": stage_main, "unseen": stage_unseen, "paths": stage_paths, "assemble": stage_assemble, "economics": lambda: __import__("ml_train.economics_prep", fromlist=["prepare"]).prepare()}[sys.argv[1]]()
