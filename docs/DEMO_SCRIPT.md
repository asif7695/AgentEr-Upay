# Demo script: 5-minute judge flow

**Setup (30 s before).** Reset the data so the clock is at 1 Sep: `scripts\seed.ps1`, restart the API, then `scripts\dev.ps1`. Open `http://localhost:3000`. Two browser windows: **Admin** (desktop) and **Agent A01** (phone-width window or device toolbar). Both start on the login page; use the one-click buttons (Admin, or an Agent ID such as `Agent A01` with password `agenta01`).

Say once, at the start: *"Everything is synthetic data. The app gives recommendations; people decide. No LLM makes any number."*

---

### 0:00 · Admin overview (the "so what")
1. Admin window, **Overview**. Clock reads **Mon 1 Sep 2025**. Point at the KPI tiles: 4 agents HIGH, model-estimated unserved demand, planned top-up total.
2. Say: *"16 agents ranked by risk of running out before the next top-up can arrive."* Click **Advance 1 day** (top bar). The banner shows the nightly pipeline: ledger rows ingested, report requested, forecasts recomputed, alerts raised.

### 0:45 · Click a WATCH agent that the habit rule would miss
3. After the advance (**Tue 2 Sep**), **A01 (Dhaka, garment)** is **WATCH** with ~40% cash risk, while its cash is still **~37% of capacity, above the agent's own 30% reorder level**. A static "alert below 30%" rule is silent. Click **A01**.
4. Read the headline: cash run-out risk before the next possible top-up, the likely run-out **date** (Fri 5 Sep), and the **suggested top-up ≈ BDT 23,214 by Thu 4 Sep** ("a cash top-up converts e-float to cash").
5. One line on why two numbers exist (the grey info box): *"over 7 days of doing nothing everyone looks risky; the actionable number is the risk before help can arrive."*

### 1:45 · Read the "Why"
6. Scroll to **Why this forecast**, pick **Sun 7 Sept**. Read the top driver aloud: *"garment-area agent × salary week: yes, +BDT 32,728"*; garment shops pay wages on the 7th to 10th, so cash-out demand nearly doubles (median ~BDT 101k vs ~57k on an ordinary day). Then the sign-aware line: *"public holiday: no, +2,233 means it is not a holiday, so demand is higher than the all-days average."*
7. Show the fan charts (P10–P90 band, shaded closed Fri/Sat) and the cash balance projection crossing the red buffer line. Toggle **Demo reveal**: the yellow diamonds are what really happened (clearly labelled synthetic ground truth, admin only).

### 2:45 · Dispatch plan
8. **Dispatch plan**: next working day (Wed 3 Sep), grouped by division, emergency orders first (A15, A11: HIGH and the next top-up lands on the run-out date), A01 as a *planned* order. Click **Acknowledge** on A01, then **Schedule**, then **Mark done** to show the order lifecycle (planned vs emergency tracked; capital-needed flags appear where a division's agents cannot cover the window).
9. Optional 20 s: **Rules & events** → add a "Fair, ×1.8, cash-out" event for Dhaka → forecast changes and is labelled *manual adjustment, not learned by the model*; change coverage to 90% and see recommendations re-run (audit log below records both).

### 3:30 · Advance a day, agent submits the cash report
10. Admin: **Advance 1 day** (Wed 3 Sep). A01's daily report is requested.
11. **Agent window** (A01, phone width): **Home** shows two gauges, status and the **Do this next** card, "Submit today's cash count" (cash is *Estimated, not confirmed today*).
12. **Daily report** tab: the form is empty. Try `-5` (validation), then enter a count more than 10% below the ledger. Instant feedback: **Needs verification**, neutral wording, ledger value used. Enter a count within tolerance: **Confirmed**, the forecast now uses the agent's count.
13. **Forecast** tab: charts and risk update immediately. Flip the language to **বাংলা** (digits switch to Bengali automatically) and the theme to dark to show the design system.

### 4:15 · Impact (say it, with the report open)
14. Offline replay, 1 Sep-24 Dec, 16 agents (synthetic): hybrid vs habit, stock-out days **64 → 29 (-55%)**, unserved **BDT 653,720 → 232,643 (-64%)**, **but orders 309 → 503 (+63%)**: *"it is not free"*. Say the uncomfortable part ourselves: **model-only (just-in-time) is worse than habit on stock-outs (76 vs 64)**; the model's value is knowing when the habit buffer is not enough.
15. Coverage is a business dial (80% → 40 days / 396 orders ... 99% → 18 / 587), and garment agents still need **capital**, not forecasts. Close on the limitations: synthetic data, one year, in-sample replay, independent-days assumption, recommendations only, needs governed upay data. (Figures are in `files/AgentEr_Upay_Project_Report.pdf` and `GET /impact`.)

---

**If something goes wrong:** *Reset to 1 Sep* (↺ in the top bar) re-runs the pipeline for that date. `Re-seed` (`scripts\seed.ps1` + API restart) clears orders, events, alerts and reports.

**Numbers to quote (all from the offline notebook):** WAPE 0.171 cash-out / 0.175 cash-in vs 0.315 / 0.303 same-weekday-last-week (noise floor 0.161); 80% interval actually covers 77.0% / 75.3%; unseen festival (Eid-ul-Adha held out) 0.292 / 0.229.

