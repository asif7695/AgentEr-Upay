"""Estimate multi-day dependence (Gaussian / AR(1) / Student-t copula) from the residuals of our calibrated challenger,
and test the simulated 3-/7-day tails out-of-sample. Writes app/data/error_correlation.json and ml_train/out/paths.json.

    python scripts/estimate_correlation.py        (needs `python -m ml_train.run main` first; see ml_train/run.py)
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from ml_train.run import stage_paths  # noqa: E402

if __name__ == "__main__":
    stage_paths()
