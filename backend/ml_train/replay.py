"""Day-by-day policy replay on the agents' demand, vectorised over agents.

The replay does NOT use ground truth: demand on a stock-out day is imputed as max(observed, the model's P75 for that day),
the same censoring-aware idea used to train. Balances follow the real mechanics: a cash-out serves cash and adds e-float, a
cash-in the reverse, and a top-up converts one balance into the other (total float is conserved), delivered on the next
working day after the order.

Policies (reorder trigger / order-up-to target, per balance):
  habit      : below 30% of capacity -> up to 65%                       (what agents do today)
  hybrid     : below max(30%, model level) -> up to max(65%, u * level)  (habit buffer raised by the model's requirement)
  model_only : below the model level -> up to u * level                  (just-in-time)
model level(p, b) = required holding level at coverage p with safety buffer b (b enters linearly: level = q_p + b * capacity).
"""
from __future__ import annotations

import numpy as np

HABIT_LOW, HABIT_HIGH = 0.30, 0.65


def simulate(policy: str, co, ci, working, cap_c, cap_e, cash0, ef0, req_c=None, req_e=None, b0=0.10, p_b=0.10, u=1.0,
             notice=None, q=1.0):
    """co, ci: (D, A) imputed demand; working: (D,) bool incl. a lookahead; req_*: (D, A) level at buffer b0 for the chosen coverage.
    notice (D, A) uniform draws and q: an agent only acts on a low balance on days it notices (draw < q). Calibrated so the habit
    policy reproduces the stock-out days actually recorded in the ledger; the SAME draws are used for every policy.
    Returns per-agent dict of totals over the D days."""
    D, A = co.shape
    cash, ef = cash0.astype(float).copy(), ef0.astype(float).copy()
    arr_c = np.zeros((D + 8, A))          # amount converting e-float -> cash arriving on day i
    arr_e = np.zeros((D + 8, A))          # amount converting cash -> e-float
    pend_c = np.zeros(A, bool)
    pend_e = np.zeros(A, bool)
    orders = np.zeros(A)
    unserved = np.zeros(A)
    so_days = np.zeros(A)
    gap_sum = np.zeros(A)
    min_bal = np.full(A, np.inf)
    keep_c, keep_e = 0.10 * cap_c, 0.10 * cap_e
    for d in range(D):
        # 1. deliveries scheduled for today
        if arr_c[d].any() or arr_e[d].any():
            cash += arr_c[d] - arr_e[d]
            ef += arr_e[d] - arr_c[d]
            pend_c &= arr_c[d] == 0
            pend_e &= arr_e[d] == 0
        # 2. demand: cash-ins recycle cash during the day (and cash-outs recycle e-float), so each flow can be served from the
        #    opening balance PLUS the other flow's served amount (verified on the dataset: cash-out = opening cash + cash-in on stock-out days)
        sc = np.minimum(co[d], cash + ci[d])
        se = np.minimum(ci[d], ef + sc)
        sc = np.minimum(co[d], cash + se)
        lost = (co[d] - sc) + (ci[d] - se)
        unserved += lost
        so_days += lost > 1.0
        cash, ef = cash - sc + se, ef + sc - se
        min_bal = np.minimum(min_bal, np.minimum(cash, ef))
        # 3. order decision after close; delivered on the next working day
        if policy == "habit":
            thr_c, thr_e = HABIT_LOW * cap_c, HABIT_LOW * cap_e
            tgt_c, tgt_e = HABIT_HIGH * cap_c, HABIT_HIGH * cap_e
        else:
            lc = req_c[d] - b0 * cap_c + p_b * cap_c
            le = req_e[d] - b0 * cap_e + p_b * cap_e
            gap_sum += np.maximum(0.0, lc + le - (cash + ef))
            if policy == "hybrid":
                thr_c, thr_e = np.maximum(HABIT_LOW * cap_c, lc), np.maximum(HABIT_LOW * cap_e, le)
                tgt_c, tgt_e = np.maximum(HABIT_HIGH * cap_c, u * lc), np.maximum(HABIT_HIGH * cap_e, u * le)
            else:
                thr_c, thr_e, tgt_c, tgt_e = lc, le, u * lc, u * le
            tgt_c, tgt_e = np.minimum(tgt_c, cap_c), np.minimum(tgt_e, cap_e)
        nxt = d + 1
        while nxt < len(working) and not working[nxt]:
            nxt += 1
        if nxt >= D:
            continue
        aware = np.ones(A, bool) if notice is None else notice[d] < q
        need_c = (cash < thr_c) & ~pend_c & aware
        x = np.where(need_c, np.minimum(tgt_c - cash, np.maximum(ef - keep_e, 0.0)), 0.0)
        x = np.maximum(x, 0.0)
        arr_c[nxt] += x
        pend_c |= x > 0
        orders += x > 0
        need_e = (ef < thr_e) & ~pend_e & aware
        y = np.where(need_e, np.minimum(tgt_e - ef, np.maximum(cash - x - keep_c, 0.0)), 0.0)
        y = np.maximum(y, 0.0)
        arr_e[nxt] += y
        pend_e |= y > 0
        orders += y > 0
    return dict(orders=orders, unserved=unserved, stockout_days=so_days, demand=(co.sum(0) + ci.sum(0)), gap_avg=gap_sum / D,
                final_total=cash + ef, min_balance=min_bal)
