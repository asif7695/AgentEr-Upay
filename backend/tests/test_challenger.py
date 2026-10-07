"""Our retrained + calibrated challenger model: selectable, honest evaluation, no leakage."""
import json

import numpy as np
import pytest

from app import settings
from app.ml import conformal
from app.ml.model_store import CHALLENGER_PATH, get_bundle

EVIDENCE = settings.BACKEND / "app" / "data" / "model_evidence.json"


def test_challenger_bundle_has_the_same_layout_as_the_supplied_one_and_no_generator_internals():
    ref, ch = get_bundle("reference"), get_bundle("challenger")
    assert CHALLENGER_PATH.exists() and ch is not ref
    assert ch["quantiles"] == ref["quantiles"] and set(ch["models"]) == {"co", "ci"} and ch["feature_cols"] == ref["feature_cols"]
    assert not {"base_cashout", "base_cashin", "noise_std"} & set(ch["agents"].columns)
    assert set(ch["calibration"]) == {"co", "ci"} and "calibration" not in ref        # the reference is never altered


def test_conformal_apply_keeps_quantiles_sorted_and_nonnegative_and_widens():
    Q = np.array([[10., 20., 30., 40., 50.]] * 3)
    calib = {"p10_p90": {"_all": 0.2, "rural": 0.2}, "p25_p75": {"_all": 0.1, "rural": 0.1}}
    out = conformal.apply(Q, np.array([100.] * 3), calib, ["rural"] * 3)
    assert (np.diff(out, axis=1) >= 0).all() and (out >= 0).all()
    assert out[0, 0] <= Q[0, 0] and out[0, 4] >= Q[0, 4] and out[0, 2] == Q[0, 2]     # wider tails, same median
    narrow = conformal.apply(Q, np.array([100.] * 3), {k: {"_all": -0.05} for k in calib}, ["rural"] * 3)
    assert narrow[0, 4] < Q[0, 4]                                                       # over-covering intervals can be tightened


def test_model_selector_changes_forecasts_and_is_validated(client, admin):
    a = client.get("/agents/A01/forecast?explain=false", headers=admin).json()
    assert a["model"] == {"choice": "challenger", "calibrated": True, "name": "agent-liquidity-challenger"}
    assert client.put("/admin/config", json={"model_choice": "nope"}, headers=admin).status_code == 422
    client.put("/admin/config", json={"model_choice": "reference"}, headers=admin)
    b = client.get("/agents/A01/forecast?explain=false", headers=admin).json()
    assert b["model"]["choice"] == "reference" and b["model"]["calibrated"] is False
    assert a["days"][0]["cashout"]["p50"] != b["days"][0]["cashout"]["p50"]
    # explanations work for both models
    assert client.get("/agents/A01/forecast?explain=true", headers=admin).json()["why"]["cashout"]


def test_evidence_file_reports_honest_out_of_sample_numbers():
    ev = json.loads(EVIDENCE.read_text(encoding="utf-8"))
    assert "NOT validated on real upay data" in ev["stamp"]
    f = ev["families"]
    for flow in ("co", "ci"):
        assert f["lightgbm_ours_cqr"][flow]["coverage80"] > f["lightgbm_ours"][flow]["coverage80"]      # calibration helps
        assert abs(f["lightgbm_ours_cqr"][flow]["coverage80"] - 0.80) < 0.05                            # and is close to nominal
        assert f["lightgbm_ours_cqr"][flow]["wape"] < f["same_weekday_last_week"][flow]["wape"]         # beats the naive baseline
    assert {"lightgbm_ours", "lognormal_gbm", "linear_quantile_regression", "seasonal_profile", "supplied_bundle"} <= set(f)
    assert ev["unseen_agents"] and ev["unseen_event"]["adha_held_out"]


def test_training_data_has_no_ground_truth_and_splits_do_not_overlap():
    from ml_train.data import SPLITS, load, masks
    df, F = load()
    assert not any(c.startswith(("true_", "unserved_")) for c in df.columns) and F[["yt_co", "yt_ci"]].isna().all().all()
    M = masks(F)
    assert not (M["TR"] & M["VA"]).any() and not (M["VA"] & M["CAL"]).any() and not (M["CAL"] & M["TE"]).any()
    assert F.loc[M["TR"], "target_date"].max() < F.loc[M["VA"], "target_date"].min() < F.loc[M["CAL"], "target_date"].min() < F.loc[M["TE"], "target_date"].min()


def test_model_evidence_endpoint_is_admin_only_and_carries_no_ground_truth(client, admin, agent_a01):
    assert client.get("/admin/model-evidence", headers=agent_a01).status_code == 403
    assert client.get("/admin/model-evidence").status_code == 401
    ev = client.get("/admin/model-evidence", headers=admin).json()
    assert ev["active"]["model_choice"] == "challenger" and ev["active"]["dependence_mode"] == "t_copula"
    text = json.dumps(ev)
    assert not any(k in text for k in ("true_cashout", "true_cashin", "unserved_cash", "base_cashout", "noise_std"))
    assert ev["paths"]["results"]["t_copula_nu6"]["7d"]["tail_error"] < ev["paths"]["results"]["independent"]["7d"]["tail_error"]
