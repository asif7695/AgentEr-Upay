"""Day-to-day dependence in the Monte Carlo: supplied engine unchanged, copula served through its rng interface."""
import hashlib
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from scipy import stats

from app import settings
from app.ml import liquidity_forecaster as lf
from app.ml import serving
from app.ml.dependence import CopulaRNG, ar1_corr, load_corr, nearest_psd_corr
from app.ml.model_store import get_bundle
from app.rules import business_rules as br
from conftest import login

N = 20000


def test_copula_serves_14_columns_in_order_and_fails_loudly_otherwise():
    r = CopulaRNG(1, ar1_corr(0.5, 0.2), 500)
    cols = [r.random(500) for _ in range(14)]
    assert all(c.shape == (500,) and (0 < c).all() and (c < 1).all() for c in cols)
    with pytest.raises(RuntimeError):
        r.random(500)                       # 15th call
    with pytest.raises(RuntimeError):
        CopulaRNG(1, ar1_corr(0.5, 0.2), 500).random(10)    # wrong size


def test_marginals_stay_uniform_and_dependence_is_present():
    c = ar1_corr(0.6, 0.3)
    r = CopulaRNG(3, c, N)
    u = np.column_stack([r.random(N) for _ in range(14)])
    for j in range(14):
        assert stats.kstest(u[:, j], "uniform").pvalue > 0.001            # each day's marginal is untouched
    z = stats.norm.ppf(u)
    assert abs(np.corrcoef(z[:, 0], z[:, 1])[0, 1] - 0.6) < 0.03          # adjacent days
    assert abs(np.corrcoef(z[:, 0], z[:, 7])[0, 1] - 0.30) < 0.03         # cash-out vs cash-in, same day (rho_cross)


def test_identity_correlation_matches_independent_sampling():
    b = get_bundle()
    q = np.sort(np.random.default_rng(0).uniform(1e4, 9e4, (7, 5)), axis=1)
    ind, _ = lf.sample_flows(q, q, b["quantiles"], N, np.random.default_rng(5))
    cop, _ = lf.sample_flows(q, q, b["quantiles"], N, CopulaRNG(5, np.eye(14), N))
    assert stats.ks_2samp(ind[:, 3], cop[:, 3]).pvalue > 0.001
    assert abs(np.corrcoef(cop[:, 0], cop[:, 1])[0, 1]) < 0.03


def test_positive_dependence_widens_cumulative_demand():
    b = get_bundle()
    q = np.sort(np.random.default_rng(1).uniform(1e4, 9e4, (7, 5)), axis=1)
    ind, _ = lf.sample_flows(q, q, b["quantiles"], N, np.random.default_rng(2))
    cop, _ = lf.sample_flows(q, q, b["quantiles"], N, CopulaRNG(2, ar1_corr(0.6, 0.0), N))
    assert np.cumsum(cop, axis=1)[:, -1].std() > 1.1 * np.cumsum(ind, axis=1)[:, -1].std()


def test_nearest_psd_returns_a_valid_correlation_matrix():
    bad = np.eye(14); bad[0, 1] = bad[1, 0] = 1.4
    c = nearest_psd_corr(bad)
    assert np.allclose(np.diag(c), 1) and np.linalg.eigvalsh(c).min() > 0


def test_supplied_module_untouched_and_default_path_equals_supplied_forecast_agent():
    mine = (Path(__file__).resolve().parents[1] / "app" / "ml" / "liquidity_forecaster.py").read_bytes()
    assert hashlib.sha256(mine).digest() == hashlib.sha256((settings.FILES_DIR / "liquidity_forecaster.py").read_bytes()).digest()
    b = get_bundle()
    df = pd.read_csv(settings.DATA_CSV, parse_dates=["date"])
    df = df[df.agent_id == "A01"].sort_values("date")
    o = pd.Timestamp("2025-12-10")
    st = df[df.date == o].iloc[0]
    hist = df[df.date <= o][["date", "observed_cashout", "observed_cashin"]]
    row = serving.agent_row_for_serving(b, "A01")
    ref = lf.forecast_agent(b, hist, lf.get_agent_row(b, "A01"), o, st.closing_cash, st.closing_efloat, seed=5)
    mine = serving.run_forecast(b, hist, row, o, st.closing_cash, st.closing_efloat, b["risk_config"], None, seed=5, dependence=None)
    assert mine["cash_risk_pct_7d"] == ref["cash_risk_pct_7d"]
    cor = serving.run_forecast(b, hist, row, o, st.closing_cash, st.closing_efloat, b["risk_config"], None, seed=5,
                               dependence=ar1_corr(0.5, 0.2))
    assert cor["cash_risk_pct_by_day"][0] == pytest.approx(ref["cash_risk_pct_by_day"][0], abs=6)   # day 1 is nearly unaffected
    assert not np.allclose(cor["cash_risk_pct_by_day"], ref["cash_risk_pct_by_day"])


def test_estimated_matrix_is_loadable_for_every_agent_type():
    for t in ("garment_urban", "market_urban", "remittance_urban", "rural", "university_urban"):
        c = load_corr(t)
        assert c is not None and c.shape == (14, 14)


def test_rule_validation_and_cache_split(client, admin):
    r = client.put("/admin/config", json={"dependence_mode": "nope"}, headers=admin)
    assert r.status_code == 422
    h_c = br.config_hash({**br.DEFAULT_RULES, "dependence_mode": "t_copula"})
    h_i = br.config_hash({**br.DEFAULT_RULES, "dependence_mode": "independent"})
    assert h_c != h_i
    f = client.get("/agents/A01/forecast?explain=false", headers=admin).json()["dependence"]
    assert f["mode"] == "t_copula" and f["risk_independent"] and f["risk_correlated"]
    client.put("/admin/config", json={"dependence_mode": "independent"}, headers=admin)
    g = client.get("/agents/A01/forecast?explain=false", headers=admin).json()
    assert g["dependence"]["mode"] == "independent"
    assert g["cash"]["risk_pct"] == f["risk_independent"]["cash"]


def test_every_dependence_mode_is_selectable_and_loads(client, admin):
    from app.ml.dependence import DEPENDENCE_MODES, load_dependence
    for m in DEPENDENCE_MODES:
        d = load_dependence(m, "rural")
        assert (d is None) == (m == "independent")
        if m == "t_copula":
            assert d[1] and d[1] > 2
        assert client.put("/admin/config", json={"dependence_mode": m}, headers=admin).status_code == 200
        assert client.get("/agents/A02/forecast?explain=false", headers=admin).json()["dependence"]["mode"] == m


def test_student_t_copula_clusters_extremes_more_than_gaussian():
    N_ = 40000
    c = ar1_corr(0.3, 0.0)
    gg, tt = CopulaRNG(4, c, N_), CopulaRNG(4, c, N_, nu=4)
    a_g, b_g = gg.random(N_), gg.random(N_)
    a_t, b_t = tt.random(N_), tt.random(N_)
    joint = lambda a, b: np.mean((a > 0.99) & (b > 0.99))
    assert joint(a_t, b_t) > 1.5 * joint(a_g, b_g)
    assert stats.kstest(a_t, "uniform").pvalue > 0.001                    # marginals still uniform
