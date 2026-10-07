"""Day-to-day demand dependence for the Monte Carlo risk engine, WITHOUT touching the supplied engine.

lf.sample_flows draws its randomness only through `rng.random(n_paths)`, exactly 2*H times in a fixed order:
cash-out day 1..H, then cash-in day 1..H. `CopulaRNG` is a drop-in object that serves those 2*H calls with
**correlated** uniforms (Gaussian copula), so lf.risk_summary / lf.sample_flows run unchanged. The marginal
distribution of every single day is untouched (each column is still uniform); only the dependence between
days and between the two flows changes.

The 14x14 correlation (order: cash-out h1..h7, cash-in h1..h7) is estimated offline from the model's
probability-integral-transform residuals on safe ledger columns only (scripts/estimate_correlation.py).
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import numpy as np
from scipy.stats import norm
from scipy.stats import t as student_t

CORR_PATH = Path(__file__).resolve().parents[1] / "data" / "error_correlation.json"
N_COLS = 14   # 2 flows x H=7 days


def nearest_psd_corr(c: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    """Symmetrise, clip negative eigenvalues, renormalise to a unit diagonal (a valid correlation matrix)."""
    c = (np.asarray(c, float) + np.asarray(c, float).T) / 2
    w, v = np.linalg.eigh(c)
    c = (v * np.clip(w, eps, None)) @ v.T
    d = np.sqrt(np.diag(c))
    c = c / np.outer(d, d)
    np.fill_diagonal(c, 1.0)
    return c


def ar1_corr(rho_day: float, rho_cross: float, h: int = 7) -> np.ndarray:
    """Simple parametric fallback/test matrix: AR(1) across days within a flow, constant cross-flow link."""
    idx = np.arange(h)
    within = rho_day ** np.abs(idx[:, None] - idx[None, :])
    c = np.block([[within, rho_cross * within], [rho_cross * within, within]])
    return nearest_psd_corr(c)


class CopulaRNG:
    """Duck-typed stand-in for np.random.Generator as used by lf.sample_flows (only `.random(n)` is called).

    Pre-draws all 14 correlated uniform columns at construction (reproducible from `seed`), then returns
    them one per `.random(n_paths)` call. It fails loudly if the engine's call pattern ever changes."""

    def __init__(self, seed: int, corr: np.ndarray, n_paths: int, nu: float | None = None):
        """nu=None: Gaussian copula. nu=k: Student-t copula (same correlation, joint tail dependence: extreme days cluster)."""
        corr = nearest_psd_corr(corr)
        if corr.shape != (N_COLS, N_COLS):
            raise ValueError(f"correlation must be {N_COLS}x{N_COLS}")
        rng = np.random.default_rng(seed)
        z = rng.standard_normal((n_paths, N_COLS)) @ np.linalg.cholesky(corr).T
        if nu is None:
            self._u = norm.cdf(z)
        else:
            w = rng.chisquare(nu, size=(n_paths, 1)) / nu            # one mixing variable per path -> joint extremes
            self._u = student_t.cdf(z / np.sqrt(w), df=nu)
        self._n, self._calls = n_paths, 0

    def random(self, size=None):
        if size != self._n or self._calls >= N_COLS:
            raise RuntimeError("CopulaRNG: unexpected call pattern from the sampler")
        col = self._u[:, self._calls]
        self._calls += 1
        return col.copy()


@lru_cache(maxsize=1)
def _store() -> dict:
    if not CORR_PATH.exists():
        return {}
    return json.loads(CORR_PATH.read_text(encoding="utf-8"))


DEPENDENCE_MODES = ("correlated", "t_copula", "ar1", "independent")
# "correlated": Gaussian copula with the full estimated 14x14 matrix (per agent type)
# "t_copula"  : same matrix, Student-t copula (tail dependence)
# "ar1"       : parametric auto-regressive path model, corr(day i, day j) = rho_day^|i-j| within a flow, rho_cross across flows


def load_dependence(mode: str, location_type: str | None = None) -> tuple[np.ndarray, float | None] | None:
    """(correlation matrix, t degrees of freedom or None) for a mode, or None for "independent" / no estimate available."""
    s = _store()
    if mode == "independent" or not s:
        return None
    if mode == "ar1":
        a = s.get("ar1")
        return (ar1_corr(a["rho_day"], a["rho_cross"]), None) if a else None
    m = (s.get("by_type") or {}).get(location_type) or s.get("pooled")
    if not m:
        return None
    return nearest_psd_corr(np.array(m)), (float(s.get("t_nu", 6)) if mode == "t_copula" else None)


def load_corr(location_type: str | None = None) -> np.ndarray | None:
    """Gaussian-copula correlation for an agent type (falls back to the pooled matrix)."""
    r = load_dependence("correlated", location_type)
    return None if r is None else r[0]


def evidence() -> dict:
    """Estimation details + coverage evidence for the model card (no matrices)."""
    s = _store()
    return {k: v for k, v in s.items() if k not in ("pooled", "by_type")} | (
        {"pooled": s["pooled"]} if s.get("pooled") else {})
