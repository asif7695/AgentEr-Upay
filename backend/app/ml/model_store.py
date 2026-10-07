"""Loads the trained bundle ONCE per process. The pickle is never mutated; callers get deep copies of config."""
from __future__ import annotations

import copy
import logging
import pickle
import threading

import lightgbm
import numpy
import pandas

from .. import settings

log = logging.getLogger("upay.model")
_lock = threading.Lock()
_bundle: dict | None = None
_challenger: dict | None | bool = False      # False = not loaded yet, None = file missing
CHALLENGER_PATH = settings.BACKEND / "models" / "challenger_bundle.pkl"
MODEL_CHOICES = ("challenger", "reference")

# Generator internals that live in bundle['agents']; stripped immediately and never used or serialized.
GENERATOR_INTERNALS = ("base_cashout", "base_cashin", "noise_std")


def get_bundle(name: str = "reference") -> dict:
    """"reference" = the supplied bundle, untouched. "challenger" = our retrained + conformally calibrated bundle
    (falls back to the reference if its file is not present)."""
    if name == "challenger":
        ch = _load_challenger()
        if ch is not None:
            return ch
    global _bundle
    if _bundle is None:
        with _lock:
            if _bundle is None:
                with open(settings.BUNDLE_PATH, "rb") as f:
                    b = pickle.load(f)
                have = {"lightgbm": lightgbm.__version__, "pandas": pandas.__version__, "numpy": numpy.__version__}
                if b.get("library_versions") != have:
                    log.warning("Bundle built with %s but running %s", b.get("library_versions"), have)
                _bundle = b
    return _bundle


def _load_challenger():
    global _challenger
    if _challenger is False:
        with _lock:
            if _challenger is False:
                if CHALLENGER_PATH.exists():
                    with open(CHALLENGER_PATH, "rb") as f:
                        _challenger = pickle.load(f)
                else:
                    log.warning("No challenger bundle at %s; using the reference model", CHALLENGER_PATH)
                    _challenger = None
    return _challenger


def effective_model(name: str) -> str:
    return "challenger" if name == "challenger" and _load_challenger() is not None else "reference"


def default_risk_config() -> dict:
    """A COPY of the bundle's risk_config (the pickle itself is never touched)."""
    return copy.deepcopy(get_bundle()["risk_config"])


def bundle_info(name: str = "reference") -> dict:
    b = get_bundle(name)
    return {"name": b.get("name"), "version": b.get("version"), "trained_on": b.get("trained_on"),
            "library_versions": b.get("library_versions"), "quantiles": b["quantiles"], "horizon": b["horizon"]}
