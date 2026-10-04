"""Runtime settings (env-overridable). No secrets are committed; the JWT secret default is for local demo only."""
import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
VAR_DIR = Path(os.getenv("UPAY_VAR_DIR", BACKEND / "var"))
VAR_DIR.mkdir(parents=True, exist_ok=True)

FILES_DIR = Path(os.getenv("UPAY_FILES_DIR", ROOT / "files"))
BUNDLE_PATH = Path(os.getenv("UPAY_BUNDLE", FILES_DIR / "liquidity_model_bundle.pkl"))
DATA_CSV = Path(os.getenv("UPAY_DATA_CSV", FILES_DIR / "agent_liquidity_dataset_v2.csv"))
DB_URL = os.getenv("UPAY_DB_URL", f"sqlite:///{(VAR_DIR / 'upay.db').as_posix()}")

JWT_SECRET = os.getenv("UPAY_JWT_SECRET", "dev-only-secret-change-me-0123456789abcdef")
JWT_ALG = "HS256"
JWT_TTL_HOURS = 12

CORS_ORIGINS = [o for o in os.getenv("UPAY_CORS", "http://localhost:3000,http://127.0.0.1:3000").split(",") if o]

# Simulation clock bounds (see README "Assumptions").
SIM_MIN_DATE = "2025-01-28"      # earliest date with >= 28 days of history
SIM_MAX_DATE = "2025-12-31"
SIM_DEFAULT_DATE = "2025-09-01"
REVEAL_MAX_DATE = "2025-12-24"   # last origin with a full 7-day outcome overlay

HISTORY_DAYS = 60                # days of ledger history passed to the serving path
FORECAST_CACHE_SIZE = 2048
