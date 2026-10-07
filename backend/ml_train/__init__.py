"""Our own model-development pipeline (retraining, comparison, calibration, honest evaluation).

The supplied bundle + serving module stay untouched as the *reference* model. Everything here is offline
and uses SAFE ledger columns only: ground-truth columns (true_*, unserved_*) are dropped before any feature is
built, so labels are the OBSERVED (censored) flows plus the stock-out flags, exactly what a real system has.
"""
