"""Offline: estimate day-to-day / cross-flow dependence of the model's forecast errors (safe ledger columns only).

For every (agent, origin) the supplied feature builder + quantile models give the predictive distribution of each
of the next 7 days. Each observed outcome is turned into a probability-integral-transform value
u = F(y) (piecewise-linear CDF through the predicted quantiles, same tails as lf._inverse_cdf) and then
z = Phi^-1(u). The 14x14 correlation of z (cash-out h1..h7, cash-in h1..h7) is what CopulaRNG uses.
Stock-out days are censored (demand was not fully observed) and are excluded, pairwise.

Writes backend/app/data/error_correlation.json, including evidence: coverage of the 80% / 95% interval of
CUMULATIVE cash-out over 3 and 7 days under independent vs correlated sampling.

    python backend/scripts/estimate_correlation.py
"""
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import settings  # noqa: E402
from app.ml import liquidity_forecaster as lf  # noqa: E402
from app.ml.dependence import CORR_PATH, CopulaRNG, nearest_psd_corr  # noqa: E402
from app.ml.model_store import get_bundle  # noqa: E402

H = lf.H


def pit(y, q, levels):
    """Forward CDF at y given predicted quantiles q (same tail rule as lf._inverse_cdf)."""
    lo = max(0.0, q[0] - 0.75 * (q[2] - q[0]))
    hi = q[-1] + 0.75 * (q[-1] - q[2])
    xs = np.concatenate([[lo], q, [hi]])
    xs = np.maximum.accumulate(xs + 1e-9 * np.arange(len(xs)))      # strictly increasing for interp
    return float(np.clip(np.interp(y, xs, np.concatenate([[0.0], levels, [1.0]])), 1e-3, 1 - 1e-3))


def main():
    bundle = get_bundle()
    levels = np.asarray(bundle["quantiles"], float)
    df = pd.read_csv(settings.DATA_CSV, parse_dates=["date"])
    f = lf.make_features(df)
    q = lf.predict_quantiles(bundle, f)
    f = f.assign(**{f"q_co_{i}": q["co"][:, i] for i in range(len(levels))}, **{f"q_ci_{i}": q["ci"][:, i] for i in range(len(levels))})
    cens = df[["agent_id", "date", "cash_stockout", "efloat_stockout"]].rename(columns={"date": "target_date"})
    f = f.merge(cens, on=["agent_id", "target_date"], how="left")
    typ = df.drop_duplicates("agent_id").set_index("agent_id")["location_type"]
    f["location_type"] = f["agent_id"].map(typ)
    qc = [f"q_co_{i}" for i in range(len(levels))]
    qi = [f"q_ci_{i}" for i in range(len(levels))]

    z_co = [norm.ppf(pit(y, qq, levels)) for y, qq in zip(f["y_co"].to_numpy(), f[qc].to_numpy())]
    z_ci = [norm.ppf(pit(y, qq, levels)) for y, qq in zip(f["y_ci"].to_numpy(), f[qi].to_numpy())]
    f["z_co"] = np.where(f["cash_stockout"] == 1, np.nan, z_co)       # cash-out is censored by a cash stock-out
    f["z_ci"] = np.where(f["efloat_stockout"] == 1, np.nan, z_ci)     # cash-in is censored by an e-float stock-out

    wide = f.pivot_table(index=["agent_id", "origin_date"], columns="h", values=["z_co", "z_ci"], dropna=False)
    wide.columns = [f"{a}_{b}" for a, b in wide.columns]
    order = [f"z_co_{h}" for h in range(1, H + 1)] + [f"z_ci_{h}" for h in range(1, H + 1)]
    wide = wide[order]
    typ_of = wide.index.get_level_values("agent_id").map(typ)

    def corr_of(w):
        return nearest_psd_corr(w.corr(min_periods=30).fillna(0.0).to_numpy())

    pooled = corr_of(wide)
    by_type = {t: corr_of(wide[typ_of == t]) for t in sorted(typ.unique())}

    # ---- evidence: cumulative cash-out interval coverage, independent vs correlated ----
    rng_o = np.random.default_rng(7)
    f["origin_key"] = f["agent_id"] + "|" + f["origin_date"].astype(str)
    keys = f["origin_key"].drop_duplicates().to_numpy()
    keys = keys[:: max(1, len(keys) // 1500)]
    groups = {k: g.sort_values("h") for k, g in f[f["origin_key"].isin(keys)].groupby("origin_key")}
    n_paths = 2000
    hit = {(m, k, lvl): [] for m in ("independent", "correlated") for k in (3, 7) for lvl in (0.8, 0.95)}
    for i, (key, g) in enumerate(groups.items()):
        if len(g) < H or g["cash_stockout"].fillna(0).iloc[:7].sum() > 0:
            continue
        qco, qci = g[qc].to_numpy(), g[qi].to_numpy()
        cr = by_type.get(g["location_type"].iloc[0], pooled)
        for mode, rng in (("independent", np.random.default_rng(i)), ("correlated", CopulaRNG(i, cr, n_paths))):
            n = n_paths if mode == "correlated" else n_paths
            co, _ = lf.sample_flows(qco, qci, levels, n, rng)
            cum = np.cumsum(co, axis=1)
            for k in (3, 7):
                actual = float(g["y_co"].iloc[:k].sum())
                for lvl in (0.8, 0.95):
                    lo_, hi_ = np.quantile(cum[:, k - 1], [(1 - lvl) / 2, 1 - (1 - lvl) / 2])
                    hit[(mode, k, lvl)].append(lo_ <= actual <= hi_)
    cover = {f"{m}_{k}d_{int(l * 100)}": round(float(np.mean(v)), 3) for (m, k, l), v in hit.items() if v}

    out = dict(
        order=["cashout_h1..h7", "cashin_h1..h7"],
        method="Gaussian copula on probability-integral-transform residuals of the supplied quantile model",
        dataset="synthetic v2 (2025), safe ledger columns only; stock-out (censored) days excluded; in-sample for the deployed model",
        n_origins=int(len(wide)),
        mean_adjacent_day_corr_cashout=round(float(np.mean([pooled[i, i + 1] for i in range(H - 1)])), 3),
        mean_adjacent_day_corr_cashin=round(float(np.mean([pooled[H + i, H + i + 1] for i in range(H - 1)])), 3),
        mean_cross_flow_same_day_corr=round(float(np.mean([pooled[i, H + i] for i in range(H)])), 3),
        interval_coverage_cumulative_cashout=cover,
        pooled=pooled.round(4).tolist(),
        by_type={t: m.round(4).tolist() for t, m in by_type.items()},
    )
    CORR_PATH.parent.mkdir(parents=True, exist_ok=True)
    CORR_PATH.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print({k: v for k, v in out.items() if k not in ("pooled", "by_type")})


if __name__ == "__main__":
    main()
