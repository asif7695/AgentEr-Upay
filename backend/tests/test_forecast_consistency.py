"""Train/serve consistency, the override layer, config isolation and latency budgets."""
import copy
import hashlib
import time
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app import settings
from app.ml import liquidity_forecaster as lf
from app.ml import serving
from app.ml.model_store import get_bundle
from app.services import forecasts
from app.services.context import Ctx, ledger
from conftest import login

ORIGIN = pd.Timestamp("2025-12-10")


@pytest.fixture(scope="module")
def bundle():
    return get_bundle()


@pytest.fixture(scope="module")
def a01_df():
    df = pd.read_csv(settings.DATA_CSV, parse_dates=["date"])
    return df[df.agent_id == "A01"].sort_values("date").reset_index(drop=True)


def test_serving_module_is_the_supplied_one():
    mine = (Path(__file__).resolve().parents[1] / "app" / "ml" / "liquidity_forecaster.py").read_bytes()
    theirs = (settings.FILES_DIR / "liquidity_forecaster.py").read_bytes()
    assert hashlib.sha256(mine).hexdigest() == hashlib.sha256(theirs).hexdigest()


def test_serving_features_equal_training_path(bundle, a01_df):
    """serving path (history only, builds its own future calendar) == make_features on the full dataset + predict_quantiles."""
    train_f = lf.make_features(a01_df, origins=[ORIGIN]).sort_values("h").reset_index(drop=True)
    st = a01_df[a01_df.date == ORIGIN].iloc[0]
    hist = a01_df[a01_df.date <= ORIGIN][["date", "observed_cashout", "observed_cashin"]]
    serve_f = serving.serving_features(bundle, hist, serving.agent_row_for_serving(bundle, "A01"), ORIGIN, st.closing_cash, st.closing_efloat)
    cols = bundle["feature_cols"]
    pd.testing.assert_frame_equal(train_f[cols].astype(float), serve_f[cols].astype(float), check_exact=False, rtol=1e-9)
    qt, qs = lf.predict_quantiles(bundle, train_f), lf.predict_quantiles(bundle, serve_f)
    assert np.allclose(qt["co"], qs["co"]) and np.allclose(qt["ci"], qs["ci"])


def test_run_forecast_equals_lf_forecast_agent(bundle, a01_df):
    st = a01_df[a01_df.date == ORIGIN].iloc[0]
    hist = a01_df[a01_df.date <= ORIGIN][["date", "observed_cashout", "observed_cashin"]]
    row = serving.agent_row_for_serving(bundle, "A01")
    ref = lf.forecast_agent(bundle, hist, lf.get_agent_row(bundle, "A01"), ORIGIN, st.closing_cash, st.closing_efloat, seed=5)
    mine = serving.run_forecast(bundle, hist, row, ORIGIN, st.closing_cash, st.closing_efloat, bundle["risk_config"], None, seed=5)
    for k in ("cashout_q", "cashin_q", "expected_cashout", "cash_risk_pct_by_day", "efloat_risk_pct_by_day", "p_cashout_surge"):
        assert np.allclose(ref[k], mine[k]), k
    for k in ("recommended_cash_level", "recommended_efloat_level", "topup_cash_needed", "coverage_window_days", "float_insufficient"):
        assert ref[k] == mine[k], k


def test_generator_internals_are_dropped_from_serving_row(bundle):
    row = serving.agent_row_for_serving(bundle, "A01")
    assert not {"base_cashout", "base_cashin", "noise_std"} & set(row.index)


def test_event_override_scales_quantiles_before_risk(bundle, a01_df):
    st = a01_df[a01_df.date == ORIGIN].iloc[0]
    hist = a01_df[a01_df.date <= ORIGIN][["date", "observed_cashout", "observed_cashin"]]
    row, cfg = serving.agent_row_for_serving(bundle, "A01"), bundle["risk_config"]
    base = serving.run_forecast(bundle, hist, row, ORIGIN, st.closing_cash, st.closing_efloat, cfg, None, seed=1)
    m = np.ones((7, 2)); m[1:4, 0] = 2.0
    ov = serving.run_forecast(bundle, hist, row, ORIGIN, st.closing_cash, st.closing_efloat, cfg, m, seed=1)
    assert np.allclose(ov["cashout_q"][1:4], 2 * base["cashout_q"][1:4]) and np.allclose(ov["cashout_q"][[0, 4, 5, 6]], base["cashout_q"][[0, 4, 5, 6]])
    assert np.allclose(ov["cashin_q"], base["cashin_q"])
    assert ov["cash_risk_pct_7d"] >= base["cash_risk_pct_7d"]


def test_bundle_is_never_mutated_by_config_changes(client, admin):
    before = copy.deepcopy(get_bundle()["risk_config"])
    r = client.put("/admin/config", json={"buffer_frac": 0.2, "coverage_prob": 0.9}, headers=admin)
    assert r.status_code == 200
    client.get("/admin/overview", headers=admin)
    assert get_bundle()["risk_config"] == before


def test_forecast_endpoint_shape_and_five_outputs(client, agent_a01):
    p = client.get("/agents/A01/forecast", headers=agent_a01).json()
    assert len(p["days"]) == 7 and len(p["cash"]["risk_by_day"]) == 7
    W = p["cash"]["window_days"]
    assert p["cash"]["risk_pct"] == p["cash"]["risk_by_day"][W - 1] and p["efloat"]["risk_pct"] == p["efloat"]["risk_by_day"][W - 1]
    d0 = p["days"][0]
    assert {"p10", "p25", "p50", "p75", "p90", "mean", "p_surge"} <= set(d0["cashout"]) and {"p10", "p90", "mean", "p_surge"} <= set(d0["cashin"])
    assert all(len(day) == 5 for day in p["why"]["cashout"]) and all(len(day) == 5 for day in p["why"]["cashin"])
    assert len(p["bands"]["cash"]["p50"]) == 8 and p["bands"]["buffer_cash"] == round(0.1 * p["agent"]["capacity_cash"])
    assert p["cash"]["recommended_level"] is not None and "gap_vs_current" in p["cash"]
    assert p["synthetic_data"] is True


def test_forecast_rejects_future_and_too_early_dates(client, agent_a01):
    assert client.get("/agents/A01/forecast?date=2025-09-02", headers=agent_a01).status_code == 422
    assert client.get("/agents/A01/forecast?date=2025-01-27", headers=agent_a01).status_code == 422
    assert client.get("/agents/A01/forecast?date=2025-08-31&explain=false", headers=agent_a01).status_code == 200


def test_earliest_valid_date_has_28_days_of_history(client, admin):
    client.post("/sim/jump", json={"date": "2025-01-28"}, headers=admin)
    r = client.get("/agents/A01/forecast?explain=false", headers=admin)
    assert r.status_code == 200, r.text


def test_latency_budgets(client, admin):
    forecasts._cache.clear(); forecasts._expl_cache.clear()
    t = time.perf_counter()
    assert client.get("/agents/A03/forecast", headers=admin).status_code == 200
    assert time.perf_counter() - t < 1.0, "one forecast (with explanations, cold) must take < 1 s"
    forecasts._cache.clear()
    t = time.perf_counter()
    assert client.get("/admin/overview", headers=admin).status_code == 200
    assert time.perf_counter() - t < 2.0, "admin overview of 16 agents (cold) must take < 2 s"
