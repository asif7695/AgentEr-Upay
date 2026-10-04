"""
Agent Liquidity Forecaster - Synthetic Dataset Generator v2
DIU CPC x upay AI Hackathon 2026

WHAT CHANGED FROM v1 (and why)
  1. FLOAT IS CONSERVED. v1 created cash from nothing on refill and never drained
     e-float (A01 e-float grew to ~7M vs 150k capacity; zero e-float stock-outs).
     v2: cash_out moves value cash -> e-float, cash_in moves e-float -> cash,
     and top-ups are explicit conversions between the two balances.
  2. TOP-UPS ONLY ON WORKING DAYS. Distributor/bank offices are closed on
     Fri/Sat and public holidays -> stock-outs cluster before long holidays.
  3. INTRADAY SLOTS. Demand is served in 4 slots with alternating order so
     cash-ins received earlier in the day can fund later cash-outs.
  4. opening_* columns are recorded at the START of the day (after top-ups arrive).
  5. CALENDAR VERIFIED against public 2025 Bangladesh holiday lists
     (Eid-ul-Fitr Mar 31, Eid-ul-Adha Jun 7). Moon-dependent dates may be +/-1 day.

ASSUMPTIONS (all synthetic; document in ASSUMPTIONS.md)
  - Base volumes differ by location type; urban > rural.
  - Rural / university / garment / remittance-receiving agents are CASH-OUT heavy (receivers withdraw).
    Urban MARKET agents are CASH-IN heavy (senders deposit cash to send money home).
  - Garment agents: payday surge days 7-10, Eid bonus week.
  - University agents: tuition/stipend withdrawals at semester start (Feb, Jul).
  - Remittance agents: mid-month cash-out surge.
  - Weekend = Friday + Saturday. Holidays suppress demand.
  - Agents order a top-up when a balance < 30% of capacity; it arrives on the
    next working day (+0-1 day).
  - Agents self-report cash daily: 4% missing, small noise, rare large errors.
"""
import numpy as np
import pandas as pd
from datetime import date, timedelta

SEED = 42
T_SCALE = 1.0          # starting float scale (tuned so stock-out rates are realistic)
OUT_DIR = "."

# ----------------------------------------------------------------- agents ---
# id, division, type, urban, garment, remittance, agri, university,
# base_cashout, base_cashin, cap_cash, cap_efloat, noise
AG = [
 ("A01","Dhaka","garment_urban",1,1,0,0,0,55000,38000,180000,150000,0.18),
 ("A02","Dhaka","rural",0,0,1,1,0,14000,10000,55000,45000,0.22),
 ("A03","Chattogram","market_urban",1,0,0,0,0,40000,48000,160000,130000,0.20),
 ("A04","Chattogram","rural",0,0,1,1,0,12000,9000,50000,40000,0.24),
 ("A05","Rajshahi","university_urban",1,0,0,0,1,32000,22000,110000,90000,0.17),
 ("A06","Rajshahi","rural",0,0,0,1,0,10000,8000,42000,35000,0.25),
 ("A07","Khulna","market_urban",1,0,0,0,0,31000,37000,130000,110000,0.19),
 ("A08","Khulna","rural",0,0,0,1,0,9000,7500,38000,32000,0.26),
 ("A09","Barishal","market_urban",1,0,0,0,0,24000,29000,100000,85000,0.21),
 ("A10","Barishal","rural",0,0,1,1,0,8500,7000,36000,30000,0.27),
 ("A11","Sylhet","remittance_urban",1,0,1,0,0,42000,28000,140000,110000,0.20),
 ("A12","Sylhet","rural",0,0,1,1,0,16000,11000,60000,48000,0.23),
 ("A13","Rangpur","market_urban",1,0,0,1,0,22000,27000,95000,80000,0.20),
 ("A14","Rangpur","rural",0,0,0,1,0,9500,8000,40000,33000,0.26),
 ("A15","Mymensingh","university_urban",1,0,0,0,1,29000,20000,100000,82000,0.18),
 ("A16","Mymensingh","rural",0,0,0,1,0,8000,6500,35000,28000,0.24),
]
COLS = ["agent_id","division","location_type","urban","garment","remittance","agri",
        "university","base_cashout","base_cashin","capacity_cash","capacity_efloat","noise_std"]
agents = pd.DataFrame(AG, columns=COLS)

# --------------------------------------------------------------- calendar ---
START, END = date(2025,1,1), date(2025,12,31)
DATES = [START + timedelta(d) for d in range((END-START).days + 1)]

# Public holidays 2025 (cross-checked against Dhaka Tribune + public calendars).
# Moon-dependent dates (Eid, Ashura) can shift by +/-1 day. Uncertain ones omitted.
HOLIDAYS = {date(2025,2,21), date(2025,3,26), date(2025,4,14), date(2025,5,1),
            date(2025,7,6), date(2025,8,16), date(2025,10,1), date(2025,10,2),
            date(2025,12,16), date(2025,12,25)}
for d0, d1 in [(date(2025,3,29), date(2025,4,2)),     # Eid-ul-Fitr holiday window
               (date(2025,6,5),  date(2025,6,10))]:   # Eid-ul-Adha holiday window
    HOLIDAYS |= {d0 + timedelta(i) for i in range((d1-d0).days + 1)}
EID_FITR, EID_ADHA = pd.Timestamp("2025-03-31"), pd.Timestamp("2025-06-07")

def build_calendar():
    c = pd.DataFrame({"date": pd.to_datetime(DATES)})
    c["day_of_week"]  = c.date.dt.dayofweek          # Mon=0 ... Fri=4, Sat=5, Sun=6
    c["day_of_month"] = c.date.dt.day
    c["month"]        = c.date.dt.month
    c["days_to_month_end"] = (c.date + pd.offsets.MonthEnd(0) - c.date).dt.days
    c["is_friday"]  = (c.day_of_week == 4).astype(int)
    c["is_saturday"]= (c.day_of_week == 5).astype(int)
    c["is_weekend"] = c.day_of_week.isin([4,5]).astype(int)
    c["is_holiday"] = c.date.dt.date.isin(HOLIDAYS).astype(int)
    c["is_working_day"] = ((c.is_weekend == 0) & (c.is_holiday == 0)).astype(int)
    c["is_salary_week"]      = c.day_of_month.between(7,10).astype(int)
    c["is_post_salary_week"] = c.day_of_month.between(11,16).astype(int)
    c["is_month_end_week"]   = (c.days_to_month_end <= 5).astype(int)
    c["days_to_eid_fitr"] = (EID_FITR - c.date).dt.days
    c["days_to_eid_adha"] = (EID_ADHA - c.date).dt.days
    # signed distance to nearest Eid, clipped (known in advance)
    both = np.stack([c.days_to_eid_fitr.abs(), c.days_to_eid_adha.abs()])
    c["days_to_nearest_eid"] = np.where(both[0] <= both[1], c.days_to_eid_fitr, c.days_to_eid_adha).clip(-30,30)
    c["is_pre_eid_fitr"] = c.days_to_eid_fitr.between(3,9).astype(int)
    c["is_pre_eid_adha"] = c.days_to_eid_adha.between(3,9).astype(int)
    c["is_eid_day"] = (c.days_to_eid_fitr.between(-1,0) | c.days_to_eid_adha.between(-1,0)).astype(int)
    c["is_eid_bonus_week"] = (c.days_to_eid_fitr.between(10,19) | c.days_to_eid_adha.between(10,19)).astype(int)
    c["is_ramadan"] = c.date.between("2025-03-02","2025-03-30").astype(int)
    c["is_semester_start"] = (((c.month==2)&(c.day_of_month<=15)) | ((c.month==7)&(c.day_of_month<=15))).astype(int)
    # consecutive non-working days ahead (how long until a top-up is possible)
    wd = c.is_working_day.values
    nxt = np.zeros(len(c), int)
    for i in range(len(c)):
        k = 1
        while i + k < len(c) and wd[i + k] == 0:
            k += 1
        nxt[i] = k - 1 if i + k < len(c) else 0
    c["closed_days_ahead"] = nxt
    return c

# ---------------------------------------------------------- demand effects ---
def cashout_mult(r, a):
    m = 1.0
    if r.is_friday: m *= 0.55
    elif r.is_saturday: m *= 0.75
    if r.is_holiday: m *= 0.20
    if r.is_eid_day: m *= 0.50
    if r.is_pre_eid_fitr or r.is_pre_eid_adha: m *= 1.90
    if a.garment and r.is_eid_bonus_week: m *= 2.00
    if a.garment and r.is_salary_week: m *= 1.80
    elif a.garment and r.is_post_salary_week: m *= 1.30
    if a.university and r.is_semester_start: m *= 1.60
    if a.remittance and r.is_post_salary_week: m *= 1.45
    if r.is_month_end_week: m *= 1.15
    if r.is_ramadan: m *= 1.25
    return m

def cashin_mult(r, a):
    m = 1.0
    if r.is_friday: m *= 0.60
    elif r.is_saturday: m *= 0.80
    if r.is_holiday: m *= 0.25
    if r.is_eid_day: m *= 0.50
    if a.urban and not a.garment and not a.university and r.is_month_end_week: m *= 1.35
    if a.remittance and r.is_post_salary_week: m *= 1.30
    if r.is_pre_eid_fitr or r.is_pre_eid_adha: m *= (1.90 if a.urban else 1.50)
    if r.is_ramadan: m *= 1.20
    return m

# ------------------------------------------------------------- simulation ---
def simulate_agent(a, cal, rng):
    cc, ce = a.capacity_cash, a.capacity_efloat
    cash, ef = 0.60 * cc * T_SCALE, 0.60 * ce * T_SCALE
    cash_floor, ef_floor = 0.15 * cc, 0.15 * ce
    pend_cash = None   # (earliest_index, amount): convert e-float -> cash
    pend_ef   = None   # (earliest_index, amount): convert cash   -> e-float
    rows = []
    for i, r in enumerate(cal.itertuples(index=False)):
        # --- 1. top-ups arrive (working days only) ---
        cash_topup = ef_topup = 0.0
        if r.is_working_day:
            if pend_cash and i >= pend_cash[0]:
                amt = min(pend_cash[1], max(0.0, ef - ef_floor))
                cash += amt; ef -= amt; cash_topup = amt; pend_cash = None
            if pend_ef and i >= pend_ef[0]:
                amt = min(pend_ef[1], max(0.0, cash - cash_floor))
                cash -= amt; ef += amt; ef_topup = amt; pend_ef = None
        open_cash, open_ef = cash, ef

        # --- 2. true demand ---
        true_co = a.base_cashout * cashout_mult(r, a) * rng.lognormal(0, a.noise_std)
        true_ci = a.base_cashin  * cashin_mult(r, a)  * rng.lognormal(0, a.noise_std)

        # --- 3. serve in 4 intraday slots, alternating order ---
        served_co = served_ci = 0.0
        for s in range(4):
            co_s, ci_s = true_co / 4, true_ci / 4
            def do_out():
                nonlocal cash, ef, served_co
                x = min(co_s, cash); cash -= x; ef += x; served_co += x
            def do_in():
                nonlocal cash, ef, served_ci
                x = min(ci_s, ef); ef -= x; cash += x; served_ci += x
            (do_out, do_in)[s % 2 == 1]() ; (do_in, do_out)[s % 2 == 1]()
        unserved_co, unserved_ci = true_co - served_co, true_ci - served_ci

        # --- 4. daily self-report of physical cash ---
        missing = rng.random() < 0.04
        big = rng.random() < 0.01
        err = rng.normal(0, cash * (0.15 if big else 0.03))
        reported = None if missing else round(cash + err)
        gap = None if missing else round(err)

        # --- 5. end-of-day: agent orders a top-up if a balance is low ---
        if pend_cash is None and cash < 0.30 * cc:
            pend_cash = (i + 1 + int(rng.integers(0, 2)), 0.65 * cc - cash)
        if pend_ef is None and ef < 0.30 * ce:
            pend_ef = (i + 1 + int(rng.integers(0, 2)), 0.65 * ce - ef)

        rows.append(dict(
            agent_id=a.agent_id, division=a.division, location_type=a.location_type, date=r.date.date(),
            day_of_week=r.day_of_week, day_of_month=r.day_of_month, month=r.month,
            days_to_month_end=r.days_to_month_end, is_weekend=r.is_weekend, is_friday=r.is_friday,
            is_holiday=r.is_holiday, is_working_day=r.is_working_day, closed_days_ahead=r.closed_days_ahead,
            is_eid_day=r.is_eid_day, is_pre_eid_fitr=r.is_pre_eid_fitr, is_pre_eid_adha=r.is_pre_eid_adha,
            is_eid_bonus_week=r.is_eid_bonus_week, days_to_nearest_eid=r.days_to_nearest_eid,
            is_ramadan=r.is_ramadan, is_salary_week=r.is_salary_week,
            is_post_salary_week=r.is_post_salary_week, is_month_end_week=r.is_month_end_week,
            is_semester_start=r.is_semester_start,
            urban=a.urban, garment=a.garment, remittance=a.remittance, agri=a.agri, university=a.university,
            agent_capacity_cash=cc, agent_capacity_efloat=ce,
            opening_cash=round(open_cash), opening_efloat=round(open_ef),
            cash_topup=round(cash_topup), efloat_topup=round(ef_topup),
            true_cashout_demand=round(true_co), true_cashin_demand=round(true_ci),
            observed_cashout=round(served_co), observed_cashin=round(served_ci),
            closing_cash=round(cash), closing_efloat=round(ef),
            unserved_cashout=round(unserved_co), unserved_cashin=round(unserved_ci),
            cash_stockout=int(unserved_co > 0.02 * true_co),
            efloat_stockout=int(unserved_ci > 0.02 * true_ci),
            reported_cash=reported, report_missing=int(missing), reconciliation_gap=gap))
    return pd.DataFrame(rows)

def add_lags(d):
    d = d.sort_values(["agent_id","date"]).reset_index(drop=True)
    g = d.groupby("agent_id")
    for col in ["observed_cashout","observed_cashin"]:
        for lag in (1,7,14):
            d[f"{col}_lag{lag}"] = g[col].shift(lag)
        d[f"{col}_rolling7"] = g[col].transform(lambda x: x.shift(1).rolling(7, min_periods=1).mean())
    return d

def main():
    rng = np.random.default_rng(SEED)
    cal = build_calendar()
    daily = add_lags(pd.concat([simulate_agent(a, cal, rng) for a in agents.itertuples(index=False)],
                               ignore_index=True))
    # integrity check: total float must stay constant except through top-ups (which are conversions)
    chk = daily.assign(total=daily.closing_cash + daily.closing_efloat)
    drift = chk.groupby("agent_id").total.agg(lambda s: s.max() - s.min())
    print("Max total-float drift per agent (should be tiny, rounding only):", drift.max())
    return daily

if __name__ == "__main__":
    daily = main()
    daily.to_csv(f"{OUT_DIR}/agent_liquidity_dataset_v2.csv", index=False)
    agents.to_csv(f"{OUT_DIR}/agents_metadata.csv", index=False)
    print(daily.shape)
    print("cash stock-out rate   : %.1f%%" % (daily.cash_stockout.mean() * 100))
    print("e-float stock-out rate: %.1f%%" % (daily.efloat_stockout.mean() * 100))
    print(daily.groupby("agent_id")[["cash_stockout","efloat_stockout"]].sum().T.to_string())
