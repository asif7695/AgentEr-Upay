"""Model families compared on identical splits. Each one fits on masks of F and returns BDT quantiles (N,5), sorted, >= 0.

lightgbm  : OUR retrain of the supplied recipe (relative target, agent-type x event crosses, censoring-aware
            labels, early stopping on a validation month) on a stricter time split.
lognormal_gbm : distributional boosting (log-normal predictive distribution from a mean model and a scale model).
linear_qr : linear quantile regression (classical, interpretable).
seasonal  : no-ML seasonal profile: empirical quantiles of relative demand by agent traits x weekday x holiday.
"""
from __future__ import annotations

import lightgbm as lgb
import numpy as np
import pandas as pd

from app.ml import liquidity_forecaster as lf
from .data import SEED

TAUS = lf.QUANTILES
COLS = lf.FEATURE_COLS
LGB_PARAMS = dict(objective="quantile", learning_rate=0.03, num_leaves=15, min_data_in_leaf=40, bagging_fraction=0.8,
                  bagging_freq=1, feature_fraction=0.8, lambda_l2=1.0, verbose=-1, seed=SEED)
FLOWS = (("co", "so_c"), ("ci", "so_e"))


def _rel(F, flow):
    return F[f"y_{flow}"] / F[f"{flow}_scale"]


def _finish(P, F, flow):
    return np.maximum(np.sort(P, axis=1) * F[f"{flow}_scale"].to_numpy()[:, None], 0.0)


# ------------------------------------------------------------------ lightgbm (ours)
def _fit_one(X, y, tr, va, tau, rounds=None):
    p = {**LGB_PARAMS, "alpha": tau}
    if rounds is None:
        return lgb.train(p, lgb.Dataset(X.loc[tr], y[tr]), 2000, valid_sets=[lgb.Dataset(X.loc[va], y[va])],
                         callbacks=[lgb.early_stopping(60, verbose=False)])
    return lgb.train(p, lgb.Dataset(X.loc[tr], y[tr]), rounds)


class LightGBM:
    name = "lightgbm"

    def __init__(self, taus=TAUS, censoring_aware=True):
        self.taus, self.censoring_aware = list(taus), censoring_aware
        self.models = {"co": {}, "ci": {}}
        self.info = {}

    def fit(self, F, tr, va):
        for flow, so in FLOWS:
            y = _rel(F, flow)
            if self.censoring_aware:       # on a stock-out day the observed value is only a FLOOR on demand
                c = F[so] == 1
                p1 = _fit_one(F[COLS], y, tr, va, 0.75)
                y = y.copy()
                y[c] = np.maximum(y[c], p1.predict(F.loc[c, COLS]))
            for tau in self.taus:
                m = _fit_one(F[COLS], y, tr, va, tau)
                self.models[flow][tau], self.info[(flow, tau)] = m, m.best_iteration
        return self

    def bundle(self, base: dict) -> dict:
        """Same layout as the supplied bundle so lf.predict_quantiles / lf.explain_prediction work unchanged."""
        return {**base, "models": self.models, "feature_cols": COLS, "quantiles": self.taus}

    def predict(self, F):
        out = {}
        for flow, _ in FLOWS:
            P = np.column_stack([self.models[flow][t].predict(F[COLS]) for t in self.taus])
            out[flow] = _finish(P, F, flow)
        return out


# ------------------------------------------------------------------ distributional LightGBM (log-normal)
class LogNormalGBM:
    """A different ML method: instead of one model per quantile, two boosted models give a log-normal predictive
    distribution (mean of log demand, and the typical absolute residual), and quantiles are read off it."""
    name = "lognormal_gbm"
    P = {**LGB_PARAMS, "objective": "regression"}

    def fit(self, F, tr, va):
        from scipy.stats import norm
        self.z = norm.ppf(TAUS)
        self.mu, self.sg = {}, {}
        for flow, so in FLOWS:
            y = np.log(np.maximum(_rel(F, flow), 0.02))
            ok = F[so] == 0
            self.mu[flow] = lgb.train(self.P, lgb.Dataset(F.loc[tr & ok, COLS], y[tr & ok]), 2000,
                                      valid_sets=[lgb.Dataset(F.loc[va & ok, COLS], y[va & ok])], callbacks=[lgb.early_stopping(60, verbose=False)])
            res = (y - self.mu[flow].predict(F[COLS])).abs()                      # in-sample residual size -> scale model
            self.sg[flow] = lgb.train({**self.P, "learning_rate": 0.05}, lgb.Dataset(F.loc[tr & ok, COLS], res[tr & ok]), 150)
        return self

    def predict(self, F):
        out = {}
        for flow, _ in FLOWS:
            mu = self.mu[flow].predict(F[COLS])
            sg = np.maximum(self.sg[flow].predict(F[COLS]) * 1.2533, 0.02)        # mean |N(0,s)| = 0.7979 s  ->  s = mean|r| * 1.2533
            out[flow] = _finish(np.exp(mu[:, None] + sg[:, None] * self.z[None, :]), F, flow)
        return out


# ------------------------------------------------------------------ linear quantile regression
class LinearQR:
    name = "linear_quantile_regression"

    def fit(self, F, tr, va):
        from sklearn.linear_model import QuantileRegressor
        from sklearn.preprocessing import StandardScaler
        self.sc = StandardScaler().fit(F.loc[tr, COLS])
        rows = F[tr | va]
        sub = rows.sample(min(len(rows), 12000), random_state=SEED)       # LP solver cost grows fast with rows
        X = self.sc.transform(sub[COLS])
        self.models = {"co": {}, "ci": {}}
        for flow, so in FLOWS:
            y = _rel(sub, flow).to_numpy()
            k = (sub[so] == 0).to_numpy()
            for tau in TAUS:
                self.models[flow][tau] = QuantileRegressor(quantile=tau, alpha=1e-4, solver="highs").fit(X[k], y[k])
        return self

    def predict(self, F):
        X = self.sc.transform(F[COLS])
        return {flow: _finish(np.column_stack([self.models[flow][t].predict(X) for t in TAUS]), F, flow) for flow, _ in FLOWS}


# ------------------------------------------------------------------ seasonal profile (no ML)
class Seasonal:
    name = "seasonal_profile"
    KEY = lf.TRAIT_COLS + ["day_of_week", "is_holiday"]

    def fit(self, F, tr, va):
        rows = F[tr | va]
        self.tab = {}
        for flow, so in FLOWS:
            r = rows[rows[so] == 0].assign(_y=_rel(rows[rows[so] == 0], flow))
            g = r.groupby(self.KEY)["_y"]
            self.tab[flow] = (g.quantile(list(TAUS)).unstack(), r["_y"].quantile(list(TAUS)).to_numpy())
        return self

    def predict(self, F):
        out = {}
        for flow, _ in FLOWS:
            tab, glob = self.tab[flow]
            idx = pd.MultiIndex.from_frame(F[self.KEY])
            P = tab.reindex(idx).to_numpy()
            P = np.where(np.isnan(P), glob[None, :], P)
            out[flow] = _finish(P, F, flow)
        return out


class SameWeekday:
    """Point baseline (no distribution): same weekday last week. Only WAPE is meaningful."""
    name = "same_weekday_last_week"

    def predict(self, F):
        return {flow: np.repeat((F[f"{flow}_lag7_r"] * F[f"{flow}_scale"]).to_numpy()[:, None], 5, axis=1) for flow, _ in FLOWS}


class Supplied:
    """The supplied bundle, as shipped (trained on ALL of 2025, so in-sample on every date we test)."""
    name = "supplied_bundle"

    def __init__(self, bundle):
        self.b = bundle

    def predict(self, F):
        q = lf.predict_quantiles(self.b, F)
        return {"co": q["co"], "ci": q["ci"]}
