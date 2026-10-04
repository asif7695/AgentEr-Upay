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

# Generator internals that live in bundle['agents']; stripped immediately and never used or serialized.
GENERATOR_INTERNALS = ("base_cashout", "base_cashin", "noise_std")


def get_bundle() -> dict:
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


def default_risk_config() -> dict:
    """A COPY of the bundle's risk_config (the pickle itself is never touched)."""
    return copy.deepcopy(get_bundle()["risk_config"])


def bundle_info() -> dict:
    b = get_bundle()
    return {"name": b.get("name"), "version": b.get("version"), "trained_on": b.get("trained_on"),
            "library_versions": b.get("library_versions"), "quantiles": b["quantiles"], "horizon": b["horizon"]}
