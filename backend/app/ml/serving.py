"""Inference layer: history -> features -> quantiles -> (human override) -> Monte Carlo risk -> explanations.

Rule: feature building, the Monte Carlo risk engine and the explanation logic are NOT reimplemented here;
they are imported from liquidity_forecaster (the supplied serving module, copied verbatim). This file only
(1) assembles the serving frame exactly like lf.forecast_agent does, but also returns the feature rows,
(2) applies the optional human event override on the quantiles, and (3) derives balance bands from the same
Monte Carlo paths (same seed => same paths as the risk numbers).
"""
from __future__ import annotations

from datetime import timedelta

import numpy as np
import pandas as pd

from . import liquidity_forecaster as lf
from .dependence import CopulaRNG
from .model_store import GENERATOR_INTERNALS

# reverse lookup "Label" -> feature column for explain_prediction output (labels must be unique)
_LABEL_TO_FEATURE = {v: k for k, v in lf.FEATURE_LABELS.items()}
assert len(_LABEL_TO_FEATURE) == len(lf.FEATURE_LABELS), "FEATURE_LABELS must be unique to be reversible"


def agent_row_for_serving(bundle: dict, agent_id: str) -> pd.Series:
    """lf.get_agent_row, with the generator internals dropped immediately."""
    row = lf.get_agent_row(bundle, agent_id)
    return row.drop(labels=[c for c in GENERATOR_INTERNALS if c in row.index])


def serving_features(bundle: dict, history: pd.DataFrame, agent_row: pd.Series, origin,
                     closing_cash: float, closing_efloat: float) -> pd.DataFrame:
    """Builds the 7 feature rows (h=1..7) for one agent at one origin, the same way lf.forecast_agent does.
    history: DataFrame[date, observed_cashout, observed_cashin], >= 28 days ending at `origin`."""
    origin = pd.Timestamp(origin)
    hist = history[history["date"] <= origin].copy()
    hist["date"] = pd.to_datetime(hist["date"])
    fut = [origin + timedelta(i) for i in range(1, lf.H + 1)]
    all_dates = list(hist["date"]) + fut
    cal = lf.build_calendar(all_dates + [origin + timedelta(lf.H + 30)], bundle["calendar_config"]).iloc[:len(all_dates)]
    df = cal.copy()
    df["agent_id"] = agent_row["agent_id"]
    for c in lf.TRAIT_COLS:
        df[c] = agent_row[c]
    df["agent_capacity_cash"], df["agent_capacity_efloat"] = agent_row["capacity_cash"], agent_row["capacity_efloat"]
    df["observed_cashout"] = list(hist["observed_cashout"]) + [np.nan] * lf.H
    df["observed_cashin"] = list(hist["observed_cashin"]) + [np.nan] * lf.H
    df["closing_cash"], df["closing_efloat"] = closing_cash, closing_efloat
    f = lf.make_features(df, origins=[origin])
    if f.empty:
        raise ValueError("Need at least 28 days of history ending at the origin date.")
    return f.sort_values("h").reset_index(drop=True)


def run_forecast(bundle: dict, history: pd.DataFrame, agent_row: pd.Series, origin, cash: float, efloat: float,
                 risk_cfg: dict, event_mult: np.ndarray | None = None, seed: int = 0,
                 dependence: np.ndarray | None = None) -> dict:
    """Full forecast. With event_mult=None and dependence=None this equals lf.forecast_agent(..., seed) numerically (tested).
    dependence: optional 14x14 correlation (see ml/dependence.py); the supplied engine runs unchanged on correlated draws."""
    f = serving_features(bundle, history, agent_row, origin, cash, efloat)
    q = lf.predict_quantiles(bundle, f)
    q_co, q_ci = q["co"], q["ci"]
    if event_mult is not None and not np.allclose(event_mult, 1.0):
        # HUMAN OVERRIDE applied to the forecast quantiles BEFORE the risk simulation (not learned by the model)
        q_co, q_ci = q_co * event_mult[:, [0]], q_ci * event_mult[:, [1]]
    r = f.iloc[0]
    cap_c, cap_e = float(r["cap_cash"]), float(r["cap_ef"])
    cfg = {**lf.DEFAULT_RISK_CONFIG, **risk_cfg}
    make_rng = (lambda: np.random.default_rng(seed)) if dependence is None else (lambda: CopulaRNG(seed, dependence, cfg["n_paths"]))
    out = lf.risk_summary(q_co, q_ci, bundle["quantiles"], cash, efloat, cap_c, cap_e, int(r["closed_ahead_origin"]),
                          r["co_scale"], r["ci_scale"], risk_cfg, make_rng())

    # Balance projection bands from the SAME Monte Carlo paths as the risk numbers (same seed, same first rng draw).
    co, ci = lf.sample_flows(q_co, q_ci, bundle["quantiles"], cfg["n_paths"], make_rng())
    cum = np.cumsum(co - ci, axis=1)
    cash_path, ef_path = cash - cum, efloat + cum
    W = int(out["coverage_window_days"])
    pct = lambda a: np.percentile(a, [10, 50, 90], axis=0)
    cb, eb = pct(cash_path), pct(ef_path)
    # model-estimated unserved demand inside the coverage window (per path, the amount the balance cannot cover)
    short_c = np.maximum(0.0, cum[:, :W].max(axis=1) - cash)
    short_e = np.maximum(0.0, (-cum[:, :W]).max(axis=1) - efloat)
    out.update(
        mean_cashout=co.mean(0), mean_cashin=ci.mean(0),
        bands=dict(cash=dict(p10=cb[0], p50=cb[1], p90=cb[2]), efloat=dict(p10=eb[0], p50=eb[1], p90=eb[2])),
        expected_unserved=dict(cash=float(short_c.mean()), efloat=float(short_e.mean())),
        cap_cash=cap_c, cap_efloat=cap_e, buffer_cash=cfg["buffer_frac"] * cap_c, buffer_efloat=cfg["buffer_frac"] * cap_e,
        co_scale=float(r["co_scale"]), ci_scale=float(r["ci_scale"]), closed_days_ahead=int(r["closed_ahead_origin"]),
        quantile_levels=list(bundle["quantiles"]), risk_cfg_used={k: cfg[k] for k in ("buffer_frac", "coverage_prob",
                                                                                   "min_order_frac", "n_paths", "surge_multiple")},
    )
    return out


def explain_days(bundle: dict, history: pd.DataFrame, agent_row: pd.Series, origin, cash: float, efloat: float,
                 top: int = 5) -> dict:
    """Top drivers per forecast day and flow via lf.explain_prediction (exact tree-SHAP, BDT).
    Returns structured items so the UI can localise the text: label, value, flag, bdt, feature key."""
    f = serving_features(bundle, history, agent_row, origin, cash, efloat)
    res = {"cashout": [], "cashin": [], "baseline_cashout": [], "baseline_cashin": []}
    for h in range(lf.H):
        row = f.iloc[[h]]
        for flow, key in (("co", "cashout"), ("ci", "cashin")):
            pairs, base = lf.explain_prediction(bundle, row, flow, top=top)
            items = []
            for text, bdt in pairs:
                label, _, val = text.rpartition(": ")
                items.append(dict(feature=_LABEL_TO_FEATURE.get(label), label=label, value=val,
                                  flag=val if val in ("yes", "no") else None, bdt=bdt, text=text))
            res[key].append(items)
            res[f"baseline_{key}"].append(base)
    return res
