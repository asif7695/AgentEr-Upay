"""Data + chronological splits. Ground truth is dropped on load: nothing here can see true demand."""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import settings  # noqa: E402
from app.ml import liquidity_forecaster as lf  # noqa: E402

GROUND_TRUTH = ["true_cashout_demand", "true_cashin_demand", "unserved_cashout", "unserved_cashin"]
INTERNALS = ["base_cashout", "base_cashin", "noise_std"]
SEED = 42

# chronological split on the TARGET date (never random: a random split leaks the future)
SPLITS = dict(
    train_end="2025-06-30",          # fit
    val=("2025-07-01", "2025-07-31"),  # early stopping
    cal=("2025-08-01", "2025-08-31"),  # conformal calibration (never used to fit)
    test_start="2025-09-01",         # untouched until reporting
)
ADHA = ("2025-05-19", "2025-06-20")   # Eid-ul-Adha window used for the unseen-event test


def load():
    df = pd.read_csv(settings.DATA_CSV, parse_dates=["date"]).sort_values(["agent_id", "date"]).reset_index(drop=True)
    df = df.drop(columns=[c for c in GROUND_TRUTH + INTERNALS if c in df.columns])
    F = lf.make_features(df)
    stock = df[["agent_id", "date", "cash_stockout", "efloat_stockout"]].rename(
        columns={"date": "target_date", "cash_stockout": "so_c", "efloat_stockout": "so_e"})
    F = F.merge(stock, on=["agent_id", "target_date"], how="left")
    typ = df.drop_duplicates("agent_id").set_index("agent_id")["location_type"]
    F["location_type"] = F["agent_id"].map(typ)
    assert not any(c in F.columns for c in GROUND_TRUTH) and F[["yt_co", "yt_ci"]].isna().all().all()
    return df, F.reset_index(drop=True)


def masks(F: pd.DataFrame) -> dict:
    t = F["target_date"]
    s = SPLITS
    return dict(
        TR=t <= s["train_end"], VA=t.between(*s["val"]), CAL=t.between(*s["cal"]), TE=t >= s["test_start"],
        ADHA=t.between(*ADHA),
    )


def uncensored(F: pd.DataFrame, flow: str) -> pd.Series:
    """True where the observed value is the real demand (the agent did not run out that day)."""
    return F["so_c" if flow == "co" else "so_e"] == 0
