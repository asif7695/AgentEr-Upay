# AgentEr Upay

**Know before you run out.** 7-day cash and e-float liquidity forecasting for upay mobile-financial-service agents.

Built for the **AI DEV FEST 2026 AI Hackathon** (DIU CPC × upay), Daffodil International University.

![Python](https://img.shields.io/badge/Python-3.12-3776AB?logo=python&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-0.142-009688?logo=fastapi&logoColor=white)
![Next.js](https://img.shields.io/badge/Next.js-16-000000?logo=nextdotjs&logoColor=white)
![TypeScript](https://img.shields.io/badge/TypeScript-5-3178C6?logo=typescript&logoColor=white)
![LightGBM](https://img.shields.io/badge/LightGBM-4.7-2E8B57)
![Tests](https://img.shields.io/badge/backend%20tests-61%20passing-brightgreen)
![Data](https://img.shields.io/badge/data-synthetic-orange)

> **Prototype on synthetic data.** All data is synthetic (16 agents × 365 days of 2025). The app gives **recommendations only**: a human agent or admin decides, nothing is autonomous. No LLM produces any number, decision or explanation.

## Table of contents

1. [Project overview](#1-project-overview)
2. [Features](#2-features)
3. [How the AI is used](#3-how-the-ai-is-used)
4. [Technology stack](#4-technology-stack)
5. [Architecture](#5-architecture)
6. [Requirements](#6-requirements)
7. [Installation and setup](#7-installation-and-setup)
8. [Environment variables](#8-environment-variables)
9. [Run and build commands](#9-run-and-build-commands)
10. [Live deployment](#10-live-deployment)
11. [Testing](#11-testing)
12. [Demo accounts and demo flow](#12-demo-accounts-and-demo-flow)
13. [API reference](#13-api-reference)
14. [Business rules](#14-business-rules)
15. [Offline evaluation results](#15-offline-evaluation-results)
16. [Other configuration](#16-other-configuration)
17. [Assumptions](#17-assumptions)
18. [Limitations](#18-limitations)
19. [Repository layout](#19-repository-layout)

---

## 1. Project overview

### The problem

An upay agent holds two balances: **cash** in the till and **e-float** in the upay wallet. A cash-out moves value from cash to e-float, a cash-in does the reverse, and a customer goes unserved the moment either balance runs out. Demand swings with weekdays, paydays, holidays and Eid and differs by agent type; replenishment is only possible on working days (Friday, Saturday and holidays are closed); agents plan by habit (reorder below roughly 30% of capacity, fill to roughly 65%); and the physical cash count is self-reported. Some agents, garment areas in particular, simply do not hold enough float.

### The proposed solution

AgentEr Upay turns "I might run low" into a specific, explained, time-bound recommendation:

1. **Forecast ranges, not one number.** A LightGBM quantile model predicts 7 days of cash-in and cash-out demand (P10 to P90).
2. **Turn risk into an action.** A Monte Carlo risk engine converts the forecast into run-out probability and a likely run-out date. Transparent business rules then say how much to top up and by when, whether the order is planned or an emergency, and whether the agent needs extra capital.
3. **Explain why, in plain language.** Each forecast shows its top drivers in taka (for example payday week, an Eid window, a weekday effect), in English and Bangla.

### Who it is for

| Role | Question answered | Surface |
|---|---|---|
| **Agent** | Will I run out, when, and what do I do today? | Mobile-first app |
| **Distributor / admin** | Which agents need an order, how urgent, how big, does anyone need more capital? | Desktop-first console |

The app replays the 2025 dataset on a **simulation clock**, so the whole daily cycle (ingest the day, request the cash report, recompute forecasts, raise alerts) can be demonstrated live.

## 2. Features

**Agent app (mobile-first)**
- Home: cash and e-float run-out gauges with status, likely run-out date, balance as a share of capacity, and a "Do this next" card.
- Daily cash report with instant, neutrally worded reconciliation against the ledger.
- 7-day forecast: demand fan charts, balance projection vs a safety buffer, risk curve, per-day table and a "Why" section.
- History of balances, top-ups and stock-out days.
- English / Bangla in one button (Bangla shows Bengali digits, English shows Latin digits); light and dark themes.

**Admin console (desktop-first)**
- Network overview: KPI tiles, division tiles and a risk-ranked, filterable agent table.
- Agent detail: the agent's forecast view plus reconciliation history, alerts and the **Demo reveal** overlay (true demand vs forecast).
- Dispatch plan: next working day's orders grouped by division and ordered by risk; planned vs emergency; order workflow (proposed → acknowledged → scheduled → done).
- Rules and events: edit buffers, coverage, thresholds, the forecast model (challenger or reference) and the path-dependence mode; add local event multipliers. Changes are validated, audit-logged and re-run forecasts without retraining.
- Model & evidence: model comparison, interval calibration, unseen-agent and unseen-event tests, and path-dependence tail risk.
- Alerts: raised on status changes, missing reports and large gaps.
- Simulation controls: advance one day, jump to a date, auto-play, reset.

**All 16 agents** (`A01` to `A16`) have their own home, report, forecast and history pages and sign in with their Agent ID.

## 3. How the AI is used

| Component | What it does | Where |
|---|---|---|
| **Challenger model (ours)**: LightGBM quantile models retrained by `backend/ml_train` | Predict P10, P25, P50, P75, P90 of cash-out and cash-in for each of the next 7 days. Relative target, agent-type × event features, censoring-aware labels, early stopping; fitted to 30 Jun on a strict chronological split | `backend/models/challenger_bundle.pkl` |
| **Conformal calibration (CQR)** | Widens or tightens the P10 to P90 and P25 to P75 intervals using a calibration month the model never trained on, per flow and agent type, so the 80% interval actually covers about 80% | `backend/app/ml/conformal.py` |
| **Reference model** (supplied LightGBM bundle) | The organisers' model, kept untouched as a selectable reference. Trained on all of 2025, so its Sep to Dec numbers are in-sample | `liquidity_model_bundle.pkl` |
| **Monte Carlo risk engine** (supplied) | Samples demand paths, applies them to current balances, returns run-out risk per day, likely run-out date, expected shortfall and the inventory level that covers the chosen coverage (95% default) | `lf.risk_summary` |
| **Multi-day path dependence** | A Student-t copula (default), Gaussian copula or AR(1) path model feeds the supplied engine correlated draws, so a high-demand day raises the next days' demand and extreme days cluster | `backend/app/ml/dependence.py` |
| **Exact tree-SHAP explanations** (supplied function) | Top-5 drivers per day in BDT, mapped to Bangla/English labels with sign-aware wording | `lf.explain_prediction` |

Model development and evidence (`backend/ml_train/`, offline, reproducible, admin page **Model & evidence**):
- **Compared on identical splits:** our LightGBM, a log-normal boosted model, linear quantile regression, a no-ML seasonal profile, the same-weekday baseline, and the supplied bundle.
- **Honest out-of-sample tests:** chronological split (fit to 30 Jun, early stopping in Jul, calibration in Aug, **test 1 Sep to 31 Dec**), 4-fold **unseen agents**, and a held-out **Eid-ul-Adha**.
- **Interval coverage:** 80% interval coverage goes from 72.1% / 75.3% (cash-out / cash-in) to 82.3% / 81.2% after calibration.
- **Path dependence:** tested on observed 3- and 7-day cumulative demand; the Student-t copula has the lowest 7-day tail error (1.8% vs 3.0% for independent days).
- Re-run on real data in the same format: `python -m ml_train.run main unseen paths assemble` (from `backend/`).

Guardrails:
- The supplied serving module is used unchanged: `backend/app/ml/liquidity_forecaster.py` is a byte-identical copy of `files/liquidity_forecaster.py` and a test asserts this. Feature building, the Monte Carlo risk engine and the explanations are imported, never reimplemented. The supplied model file is never modified; our own models are separate files.
- **No ground truth in training or evaluation:** ground-truth columns are dropped before any feature is built, and a test enforces it.
- **Model vs rules are separate.** Buffers, coverage, thresholds, top-up sizing and timing, reconciliation and event overrides live in `backend/app/rules/business_rules.py` and the config table. Rule changes re-run forecasts on a copy of the risk config.
- **No ground truth in the product.** True-demand columns live in an isolated table read only by the admin Demo reveal service; generator internals (`base_cashout`, `base_cashin`, `noise_std`) are never loaded or shown. A test proves no such field appears in any other response.
- **No LLM** produces any number, decision or explanation; explanations are deterministic templates.
- **Uncertainty is always shown** (bands and percentages) and every value carries its provenance (model quantile or rule name).
- A **human event override** lets people encode what the model cannot know; it is labelled "manual adjustment, not learned by the model".

## 4. Technology stack

| Layer | Technologies |
|---|---|
| Language | Python 3.12, TypeScript |
| Backend | FastAPI, Uvicorn, SQLAlchemy 2, SQLite, Pydantic 2, PyJWT, bcrypt |
| ML / data | LightGBM 4.7.0, pandas 3.0.2, numpy 2.4.4, scipy, scikit-learn (linear quantile baseline); pinned to the versions recorded in the bundle |
| Frontend | Next.js 16 (App Router), React, Tailwind CSS v4, Recharts, Framer Motion, lucide-react |
| i18n | Typed English and Bangla dictionaries; `Intl` for digits and dates |
| Testing | pytest, ESLint, TypeScript type-check via `next build` |
| Packaging | Docker, docker-compose, Makefile, PowerShell scripts |
| External services | None. No third-party APIs, no LLM, no network calls at runtime |

## 5. Architecture

```
 files/ (CSV, bundle .pkl, liquidity_forecaster.py)             browser
        │                                                         │  Next.js (App Router, TS, Tailwind, Recharts, Framer Motion)
        ▼                                                         ▼
 ┌─────────────── DATA PREPARATION ───────────────┐       ┌───────────────┐
 │ app/seeding.py  CSV -> SQLite                  │       │ REST + JWT    │
 │  daily (safe ledger cols) · reports · agents   │       └──────┬────────┘
 │  ground_truth (isolated)  · users · config     │              │
 │  generator internals are NEVER loaded          │       ┌──────▼──────────────────────────────────────┐
 └────────────────────────────────────────────────┘       │ FastAPI  routers/  (role checks in the API) │
                                                          │   services/  sim · forecasts(cache) · alerts │
 ┌────────────── MODEL INFERENCE (ml/) ────────────┐◄─────│     dispatch · overview · reveal             │
 │ model_store   bundle loaded ONCE, never mutated │      │   rules/business_rules.py  (NOT the model)   │
 │ serving       features -> quantiles ->          │      │     status bands · reconciliation · top-up   │
 │               [human override] -> Monte Carlo   │      │     timing · capital gap · event multipliers │
 │ liquidity_forecaster.py  (verbatim, imported)   │      └──────────────────────────────────────────────┘
 └─────────────────────────────────────────────────┘
```

Separation of concerns:
- **Data prep vs inference.** `seeding.py` only moves data; `ml/serving.py` only does inference.
- **Rules vs model.** See [How the AI is used](#3-how-the-ai-is-used).
- **Performance.** The bundle loads once at startup. Forecasts are cached per (agent, date, config hash, cash input, event multipliers); thresholds are applied after the cache, so editing them needs no re-simulation. Measured on a laptop: one forecast about 40 ms (about 120 ms with explanations), cold 16-agent overview about 0.8 s, full nightly pipeline about 1.2 s.

How the five required outputs map to the code:

| # | Output | Produced by |
|---|---|---|
| 1 | Cash run-out risk % (headline = `cash_risk_pct_by_day[window-1]`, 7-day curve, likely run-out date) | `lf.risk_summary` via `ml/serving.run_forecast`; headline and date in `services/forecasts._section` |
| 2 | E-float run-out risk % | same engine, other direction |
| 3 | Per-day cash-in/out distribution (P10 to P90 fan) and surge probability | `lf.predict_quantiles`, `p_cashout_surge`, `p_cashin_surge` |
| 4 | Expected amount per day (median and mean) | quantile P50 and Monte Carlo mean |
| 5 | Recommended inventory, gap, top-up with by-when date, "float too small, extra capital X" | engine's recommended levels; rules `topup_by_date`, `capital_gap` |
| + | "Why": top-5 drivers per day, BDT | `lf.explain_prediction` via `ml/serving.explain_days` |

Two risk numbers are shown on purpose: over 7 days of doing nothing risk is high for nearly everyone, so the actionable number is the risk **before the next possible top-up** (the window lengthens before weekends and holidays).

## 6. Requirements

| Requirement | Version / note |
|---|---|
| Python | 3.12 (the pinned pandas 3.0.2 / numpy 2.4.4 need a recent Python) |
| Node.js | 20 or newer (developed on 24) and npm |
| OS | Windows, macOS or Linux (developed on Windows 11) |
| Hardware | Any laptop; about 1 GB free RAM, about 1 GB disk for dependencies |
| Optional | Docker and Docker Compose, GNU make |
| Data / model files | Already in `files/` (dataset CSV and model bundle); no downloads needed |

## 7. Installation and setup

```bash
git clone https://github.com/asif7695/AgentEr-Upay.git
cd AgentEr-Upay
```

**Windows (PowerShell)**

```powershell
python -m venv backend\.venv
backend\.venv\Scripts\python -m pip install -r backend\requirements.txt
cd frontend; npm install; cd ..
scripts\seed.ps1        # CSV -> SQLite (also done automatically on first API start)
```

**macOS / Linux**

```bash
python3.12 -m venv backend/.venv
backend/.venv/bin/python -m pip install -r backend/requirements.txt
(cd frontend && npm install)
make seed
```

`make setup` does the install steps in one go. The default configuration works as-is; see [Environment variables](#8-environment-variables) to change anything.

## 8. Environment variables

All are optional for local use. **No secret values are committed**; copy `.env.example` / `frontend/.env.example` if you want to set them.

| Variable | Used by | Purpose | Default |
|---|---|---|---|
| `UPAY_JWT_SECRET` | API | Signing key for login tokens. **Set a long random value for anything but a local demo.** | dev-only placeholder |
| `UPAY_DB_URL` | API | SQLAlchemy database URL | `sqlite:///backend/var/upay.db` |
| `UPAY_VAR_DIR` | API | Folder for the SQLite file | `backend/var` |
| `UPAY_FILES_DIR` | API | Folder holding the dataset and model bundle | `files/` |
| `UPAY_BUNDLE` | API | Path to the model bundle | `files/liquidity_model_bundle.pkl` |
| `UPAY_DATA_CSV` | API | Path to the dataset CSV | `files/agent_liquidity_dataset_v2.csv` |
| `UPAY_CORS` | API | Comma-separated allowed browser origins | `http://localhost:3000,http://127.0.0.1:3000` |
| `NEXT_PUBLIC_API_URL` | Web (build time) | URL of the API as seen from the browser | `http://127.0.0.1:8000` |

## 9. Run and build commands

**Development**

```powershell
scripts\dev.ps1                # Windows: opens API :8000 and web :3000 in two windows
```

```bash
make dev                       # macOS / Linux: API :8000 and web :3000
```

Or manually, in two terminals:

```bash
cd backend  && ../backend/.venv/bin/python -m uvicorn app.main:app --port 8000      # Windows: ..\backend\.venv\Scripts\python
cd frontend && npm run dev
```

- API docs (Swagger): http://127.0.0.1:8000/docs
- Web app: http://localhost:3000

**Production build**

```bash
cd frontend && npm run build && npm run start -- --port 3000
cd backend  && ../backend/.venv/bin/python -m uvicorn app.main:app --host 0.0.0.0 --port 8000
```

**Docker**

```bash
docker compose up --build      # api :8000, web :3000
```

Note: the Docker files are provided but were not run on the build machine (Docker was not installed there); the local virtual-environment and npm path is the verified one.

**Re-seed** (resets the clock to 1 Sep 2025 and clears orders, events, alerts and reports): `scripts\seed.ps1` or `make seed`, then restart the API.

## 10. Live deployment

**Live URL: not deployed yet.** The project is runnable locally in a few minutes using the steps above (API http://127.0.0.1:8000, web http://localhost:3000). A hosted URL will be added here once deployed.

## 11. Testing

```powershell
scripts\test.ps1               # Windows
```

```bash
make test                      # macOS / Linux  (cd backend && python -m pytest -q)
cd frontend && npm run lint && npm run build     # lint + TypeScript type-check + production build
```

The backend suite has **61 tests** (about 65 s) and uses an isolated temporary database:
- **Auth and role isolation**: all 16 agents log in with their Agent ID and can read only their own data; agent to admin endpoints returns 403; no token returns 401.
- **No leakage**: no ground-truth or generator column appears in any response outside the admin reveal.
- **Train/serve consistency**: the serving path produces the same features and quantiles as the supplied code, and `run_forecast` equals the supplied `forecast_agent`; the serving module is byte-identical to the supplied file.
- **Rules**: reconciliation edge cases (missing report, over 10%, exactly 10%, zero ledger), top-up timing, status bands, event multipliers, config validation.
- **Workflow**: clock advance, jump and end of data, alerts, orders lifecycle, audit log.
- **Latency budgets**: forecast under 1 s, overview under 2 s.

To verify by hand, follow [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md).

## 12. Demo accounts and demo flow

Mock accounts only, no personal data.

| Role | Login | Password |
|---|---|---|
| Admin | `admin` | `admin123` |
| Agent | Agent ID, e.g. `Agent A01` (also `A01` or `a01`) | `agent` + lowercase id, e.g. `agenta01` |

The login page lists all 16 agents (A01 to A16) as one-click buttons; each lands on that agent's own pages. The simulation clock starts at **2025-09-01**. A five-minute judge walkthrough is in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md). The full project report is [files/AgentEr_Upay_Project_Report.pdf](files/AgentEr_Upay_Project_Report.pdf).

## 13. API reference

JSON, JWT bearer, one error envelope `{"error":{"code","message","details"}}`. Agents can read only their own data (enforced in the API). Interactive docs at `/docs`.

| Endpoint | Purpose |
|---|---|
| `POST /auth/login`, `GET /me` | mock users (1 admin, 16 agents) |
| `GET /sim/state`, `POST /sim/advance`, `POST /sim/jump` | clock (advance and jump: admin) |
| `GET /agents` (admin), `GET /agents/{id}`, `GET /agents/{id}/forecast?date=`, `GET /agents/{id}/history` | agent data |
| `POST /agents/{id}/cash-report` | daily count; reconciles instantly |
| `GET /agents/{id}/reveal?date=` | admin-only ground-truth overlay |
| `GET /admin/overview`, `GET /admin/dispatch-plan?date=` | admin views |
| `GET/POST /admin/orders`, `PATCH /admin/orders/{id}` | planned vs emergency; proposed → acknowledged → scheduled → done / cancelled |
| `GET/PUT /admin/config`, `GET/POST /admin/events`, `DELETE /admin/events/{id}`, `GET /admin/audit` | rules, overrides, audit log |
| `GET /alerts`, `POST /alerts/{id}/ack` | scoped to the caller |
| `GET /admin/model-evidence` | model comparison, calibration, unseen tests, path dependence (admin; offline, synthetic) |
| `GET /impact`, `GET /health` | static offline-evaluation JSON (labelled synthetic), health |

The audit log records config changes, orders, cash reports, events, simulation-clock moves and failed logins.

## 14. Business rules

All live in `backend/app/rules/business_rules.py` and are documented in code.

- **Status bands** (configurable): risk ≥ 50% HIGH, 30 to 50% WATCH, below 30% OK. Agent status is the worse of cash and e-float. Always colour, icon and text.
- **Reconciliation.** E-float and flows are the ledger; physical cash is self-reported. `gap% = (reported − ledger) / ledger`. If `|gap| > 10%` the entry is "Needs verification" and the forecast uses the **ledger** value. A missing report uses the ledger estimate, labelled "Estimated, not confirmed today". Wording is neutral, never accusatory.
- **Top-up by-when** is the latest working day before the likely run-out date, never earlier than the next working day. If even the next working day is too late the order is flagged late; with HIGH risk it is an **emergency** order, otherwise **planned**.
- **Top-up meaning.** A cash top-up converts e-float to cash; an e-float top-up buys e-float with cash. If total float is too small: extra capital = required cash + required e-float − current cash − current e-float.
- **Local event override** (`POST /admin/events`): a demand multiplier with a date range, applied to the forecast quantiles before the risk simulation.
- **Demo reveal** (admin only): overlays true demand and the true outcome for the next 7 days.
- **Simulation clock.** Valid dates run from 2025-01-28 (28 days of history needed) to 2025-12-31; the reveal overlay needs 7 full days, so its last origin is 2025-12-24.

## 15. Offline evaluation results

From the supplied evaluation notebook; a **simulation on synthetic data**, not a measurement on real upay data. Policy replay: 1 Sep to 24 Dec 2025, 16 agents, 115 days.

| Policy | Stock-out days | Unserved demand (BDT) | Orders |
|---|---|---|---|
| Agent habit (order below 30%, top up to 65%) | 64 | 653,720 | 309 |
| **Hybrid** (habit buffer raised by the model's 95% requirement) | **29** | **232,643** | 503 |
| Model only (just-in-time) | 76 | 549,632 | 518 |

- Hybrid vs habit: about **55% fewer stock-out days** and **64% less unserved demand**, for about **63% more orders**. That is not free; whether it pays off depends on the cost of a trip versus an unserved customer.
- Model-only is **worse** than habit on stock-outs (76 vs 64): the model's value is knowing when the habit buffer is not enough.
- Coverage is a business dial: 80 / 90 / 95 / 99% gives 40 / 36 / 29 / 18 stock-out days for 396 / 450 / 503 / 587 orders.
- Stock-out reduction by agent type: rural 78%, university 71%, market 50%, garment 20%, remittance urban 0%. Garment agents need capital: their 95% requirement exceeds total float on 10.7% of days (average shortfall about BDT 13,062).
- Accuracy (WAPE, test Sep to Dec): model 17.1% cash-out and 17.5% cash-in vs 31.5% and 30.3% for same-weekday-last-week; synthetic noise floor 16.1%. The 80% interval actually covers 77.0% and 75.3%. Unseen agent 17.2% vs 16.9% seen; with Eid-ul-Adha held out, 29.2% cash-out and 22.9% cash-in.

## 16. Other configuration

- **Data and model files** must stay in `files/` (or point `UPAY_FILES_DIR`, `UPAY_BUNDLE`, `UPAY_DATA_CSV` elsewhere). The API seeds SQLite from the CSV on first start.
- **Version pinning.** `lightgbm 4.7.0`, `pandas 3.0.2` and `numpy 2.4.4` match the bundle's recorded library versions; the API logs a warning on mismatch.
- **Manual-report demo agent.** `manual_report_agents` (default `["A01"]`) under Rules and events keeps that agent's report pending after each advance so the report form can be shown live.
- **Brand colours.** All theme colours are CSS variables in `frontend/app/globals.css`.
- **Ports.** API 8000, web 3000. If you change the API port, set `NEXT_PUBLIC_API_URL` and `UPAY_CORS` accordingly.

## 17. Assumptions

No questions were asked during the build, so these are recorded here.

1. No upay logo was supplied: the logo mark is a placeholder and the warm yellow accent is assumed. The theme colour is navy `#0D1C42`.
2. `agents_metadata.csv` was not provided; agent traits and capacities come from the dataset's static columns (identical to the bundle's agent table). Generator internals in `bundle["agents"]` are dropped immediately after `get_agent_row` and never used or shown.
3. Some colour tokens were adjusted from the original spec to reach WCAG AA contrast for text. Chart series colours (blue and orange) were checked with a colour-blind-safe palette validator in light and dark.
4. The ledger is the dataset: orders and "mark done" are **planning records** and do not change replayed balances.
5. Cash used for the forecast is the agent's count when within tolerance, otherwise the ledger value.
6. Manual events apply to forecast target dates in their range regardless of when created; multiple events multiply.
7. "Model-estimated unserved demand" is the expected shortfall inside the coverage window from the same Monte Carlo paths, never ground truth.
8. The calendar config covers 2025 only; forecasts in the last week of December look into early January 2026 without holiday information.
9. Authentication is a demo: bcrypt-hashed mock users and an HS256 JWT with a development secret.

## 18. Limitations

- **No real upay data was available.** Retraining, calibration and the unseen-agent / unseen-event tests are out-of-sample on a chronological split, but still on synthetic data, so they validate the method and pipeline, not real-world accuracy. The pipeline re-runs unchanged on real data in the same format.
- Day-to-day dependence on this synthetic data is weak (day-to-day link about 0.1); real data may show more, and the app re-estimates it.
- Our retrained model is slightly less accurate than the supplied bundle on Sep to Dec (WAPE 0.169 vs 0.158 cash-out), because the supplied bundle was trained on those months. We keep the supplied model selectable as the reference.
- Synthetic data: the model recovers planted patterns, so results validate the pipeline, not real-world accuracy.
- One year of data only. The default (challenger) model is out-of-sample from 1 Sep 2025; the reference model and earlier replay dates are in-sample.
- The supplied risk engine assumes independent days by default; we add path dependence on top (default Student-t copula), but error by horizon is still unrealistically flat on synthetic data.
- Recommendations only; humans decide.
- Needs governed upay data for validation before any pilot.

## 19. Repository layout

```
AgentEr-Upay/
├─ files/                      supplied resources (dataset, model bundle, serving module, notebook) + project report PDF
├─ backend/
│  ├─ app/
│  │  ├─ main.py  settings.py  db.py  models.py  auth.py  errors.py  seeding.py
│  │  ├─ ml/                   model_store.py, serving.py, liquidity_forecaster.py (verbatim copy)
│  │  ├─ rules/                business_rules.py
│  │  ├─ services/             sim, forecasts, alerts, dispatch, overview, reveal, context
│  │  ├─ routers/              core, agents, admin
│  │  └─ data/impact.json      static offline-evaluation numbers
│  ├─ ml_train/                own training pipeline: families, conformal, paths, run.py (stages: main, unseen, paths, assemble)
│  ├─ models/                  challenger_bundle.pkl (our retrained, calibrated model)
│  ├─ scripts/seed.py
│  └─ tests/                   61 tests
├─ frontend/
│  ├─ app/                     login, agent/*, admin/*
│  ├─ components/              shell, design system, charts, forecast views
│  └─ lib/                     api client, i18n, dictionaries (en, bn)
├─ docs/DEMO_SCRIPT.md         five-minute judge walkthrough
├─ scripts/                    seed / dev / test PowerShell scripts
├─ docker-compose.yml  Makefile  .env.example
└─ README.md
```

## Credits

Built by Team AgentEr Upay for the AI DEV FEST 2026 AI Hackathon, organised by the DIU Computer and Programming Club (DIU-CPC), Department of CSE, Daffodil International University. The dataset, model bundle and serving module in `files/` were supplied by the organisers; the application around them was built during the hackathon. Development used Claude Code as an AI coding assistant.
