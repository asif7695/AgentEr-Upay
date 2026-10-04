"""Usage: python scripts/seed.py   (re-creates backend/var/upay.db from the CSV)"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.seeding import seed  # noqa: E402

if __name__ == "__main__":
    print(seed(force=True))
