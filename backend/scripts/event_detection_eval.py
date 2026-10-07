"""Offline evidence for the unusual-event detector (writes app/data/event_detection_eval.json).

1. False alarms: run the detector night by night over 1 Sep - 20 Dec on the UNTOUCHED ledger (synthetic data) and count how
   often it would propose something, with the same 7-day suppression the app uses.
2. Power: inject known shocks (flows multiplied for 7 days) into a copy of the ledger and record whether and how fast the
   detector notices. The model sees the shocked history, so its own lag features adapt, which is realistic and makes the
   test harder, not easier.

Run from backend/:  python -m scripts.event_detection_eval
"""
from __future__ import annotations

import json
import os
import sys
import tempfile
import time
import warnings
from datetime import date, timedelta
from pathlib import Path
from statistics import median

warnings.filterwarnings("ignore")
_tmp = tempfile.mkdtemp(prefix="upay_eval_")
os.environ["UPAY_VAR_DIR"] = _tmp
os.environ["UPAY_DB_URL"] = f"sqlite:///{Path(_tmp, 'eval.db').as_posix()}"
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.db import SessionLocal  # noqa: E402
from app.seeding import seed  # noqa: E402
from app.services import adaptive, anomalies  # noqa: E402
from app.services.context import Ctx, ledger  # noqa: E402

OUT = Path(__file__).resolve().parents[1] / "app" / "data" / "event_detection_eval.json"
START, END = date(2025, 9, 1), date(2025, 12, 20)
MAGNITUDES = (1.3, 1.5, 2.0, 0.6)


def main():
    t0 = time.time()
    seed(force=True)
    ledger.load()
    agents = sorted(ledger.agents)
    with SessionLocal() as db:
        ctx = Ctx(db)
        ctx.rules["adaptive_mode"] = "suggest"
        # ---- 1. false alarms on untouched data
        nights = proposals = flow_hits = 0
        blocked: dict[tuple, date] = {}
        d = START
        while d <= END:
            plans = anomalies._plan(ctx, d)
            nights += 1
            for p in plans:
                flow_hits += len(p["members"])
                key = (p["scope"], p["target"])
                if key in blocked and d <= blocked[key]:
                    continue
                blocked[key] = d + timedelta(days=anomalies.HORIZON)
                proposals += 1
            d += timedelta(days=1)
        agent_nights = nights * len(agents)
        fa = dict(nights=nights, agent_nights=agent_nights, detections=flow_hits, detection_rate_per_agent_night=round(flow_hits / agent_nights, 4),
                  distinct_proposals=proposals, proposals_per_week=round(7 * proposals / nights, 2), period=[START.isoformat(), END.isoformat()])
        print("false alarms:", fa, f"{time.time() - t0:.0f}s")

        # ---- 2. power under injected shocks
        trials = []
        for i, aid in enumerate(agents):
            for j, mult in enumerate(MAGNITUDES):
                start = date(2025, 9, 15) + timedelta(days=(i * 5 + j * 23) % 80)
                trials.append(dict(agent_id=aid, start=start.isoformat(), length=7, mult=mult))
        res = anomalies.evaluate_shocks(ctx, trials, END)
        adaptive.invalidate()
        power = {}
        for mult in MAGNITUDES:
            r = [x for x in res if x["mult"] == mult]
            got = [x["delay_days"] for x in r if x["detected"]]
            power[str(mult)] = dict(trials=len(r), detected=len(got), detection_rate=round(len(got) / len(r), 3),
                                    median_delay_days=median(got) if got else None, within_3_days=round(sum(1 for g in got if g <= 3) / len(r), 3))
        print("power:", power, f"{time.time() - t0:.0f}s")
    out = dict(stamp="Synthetic data; shocks injected into a COPY of the ledger (observed flows multiplied for 7 days).", false_alarms=fa, power=power,
               protocol=dict(shock_length_days=7, flows="cash-out", magnitudes=list(MAGNITUDES), agents=len(agents),
                             rule="jump: 2 days |z|>=1.64 and >=25% off median; shift: CUSUM(k=0.75,h=5), >=3 days; proposals suppressed for 7 days per scope"))
    OUT.write_text(json.dumps(out, indent=1), encoding="utf-8")
    print("written", OUT)


if __name__ == "__main__":
    main()
