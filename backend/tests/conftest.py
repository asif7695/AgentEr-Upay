import os
import shutil
import sys
import tempfile
import warnings
from pathlib import Path

# Isolated DB for tests: must be set BEFORE importing the app (settings read env at import time).
_TMP = Path(tempfile.mkdtemp(prefix="upay_test_"))
os.environ["UPAY_VAR_DIR"] = str(_TMP)
os.environ["UPAY_DB_URL"] = f"sqlite:///{(_TMP / 'test.db').as_posix()}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
warnings.filterwarnings("ignore")

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.seeding import seed  # noqa: E402
from app.services.context import ledger  # noqa: E402


def pytest_sessionfinish(session, exitstatus):
    shutil.rmtree(_TMP, ignore_errors=True)


@pytest.fixture()
def client():
    """Fresh seeded database for every test (sim clock back at 2025-09-01, default rules, no orders/events)."""
    with TestClient(app) as c:
        seed(force=True)
        ledger.load()
        yield c


def login(c, username, password):
    r = c.post("/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.text
    return {"Authorization": "Bearer " + r.json()["access_token"]}


@pytest.fixture()
def admin(client):
    return login(client, "admin", "admin123")


@pytest.fixture()
def agent_a01(client):
    return login(client, "Agent A01", "agenta01")
