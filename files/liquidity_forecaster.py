"""
liquidity_forecaster.py
Agent Liquidity Forecaster - shared logic for training, evaluation and serving.
DIU CPC x upay AI Hackathon 2026

Pipeline:  daily history -> make_features -> quantile models -> Monte Carlo roll-forward -> risk + recommendation
Design rules (from the rulebook):
  * data preparation is separate from model inference
  * business rules (buffers, coverage probability) live in `risk_config`, NOT inside the ML model
  * every output is traceable to a model quantile or a documented rule
"""
import numpy as np
import pandas as pd
from datetime import date, timedelta

H = 7                                   # forecast horizon (days)
QUANTILES = [0.10, 0.25, 0.50, 0.75, 0.90]
MIN_HIST = 28                           # days of history needed at the forecast origin

CAL_COLS = ["day_of_week", "day_of_month", "month", "days_to_month_end", "is_weekend", "is_friday",
            "is_holiday", "is_working_day", "closed_days_ahead", "is_eid_day", "is_pre_eid_fitr",
            "is_pre_eid_adha", "is_eid_bonus_week", "days_to_nearest_eid", "is_ramadan",
            "is_salary_week", "is_post_salary_week", "is_month_end_week", "is_semester_start"]
TRAIT_COLS = ["urban", "garment", "remittance", "agri", "university"]

# Interaction features (agent type x calendar event). Payday, bonus and semester effects apply to ONE kind of
# agent only; rare, type-specific effects are hard for trees to discover from ~200 rows, so we cross them explicitly.
CROSS_EVENTS = ["is_salary_week", "is_post_salary_week", "is_month_end_week", "is_eid_bonus_week",
                "pre_eid_any", "is_semester_start", "is_ramadan"]
CROSS_COLS = [f"x_{t}_{e}" for e in CROSS_EVENTS for t in TRAIT_COLS]

DEFAULT_RISK_CONFIG = dict(
    buffer_frac=0.10,        # "effectively out" = balance below 10% of capacity
    coverage_prob=0.95,      # recommended level protects the window with 95% probability
    n_paths=2000,            # Monte Carlo paths
    surge_multiple=1.5,      # a "surge day" = demand > 1.5x the agent's 28-day mean
    min_order_frac=0.10,     # ignore top-ups smaller than 10% of capacity (not worth a trip)
)

# Official 2025 calendar used by the dataset (moon-dependent dates may shift +/-1 day).
DEFAULT_CALENDAR_CONFIG = dict(
    holidays=["2025-02-21", "2025-03-26", "2025-04-14", "2025-05-01", "2025-07-06", "2025-08-16",
              "2025-10-01", "2025-10-02", "2025-12-16", "2025-12-25"],
    holiday_windows=[("2025-03-29", "2025-04-02"), ("2025-06-05", "2025-06-10")],   # Eid holidays
    eid_fitr="2025-03-31", eid_adha="2025-06-07",
    ramadan=("2025-03-02", "2025-03-30"),
)


# ------------------------------------------------------------------ calendar --
def build_calendar(dates, cfg=None):
    """Calendar features for any list of dates. Used at serving time for FUTURE dates,
    where the dataset has no rows yet. Must reproduce the training calendar exactly."""
    cfg = cfg or DEFAULT_CALENDAR_CONFIG
    c = pd.DataFrame({"date": pd.to_datetime(list(dates))})
    hol = {pd.Timestamp(d).date() for d in cfg["holidays"]}
    for a, b in cfg["holiday_windows"]:
        a, b = pd.Timestamp(a), pd.Timestamp(b)
        hol |= {(a + timedelta(i)).date() for i in range((b - a).days + 1)}
    fitr, adha = pd.Timestamp(cfg["eid_fitr"]), pd.Timestamp(cfg["eid_adha"])
    c["day_of_week"] = c.date.dt.dayofweek
    c["day_of_month"] = c.date.dt.day
    c["month"] = c.date.dt.month
    c["days_to_month_end"] = (c.date + pd.offsets.MonthEnd(0) - c.date).dt.days
    c["is_friday"] = (c.day_of_week == 4).astype(int)
    c["is_weekend"] = c.day_of_week.isin([4, 5]).astype(int)
    c["is_holiday"] = c.date.dt.date.isin(hol).astype(int)
    c["is_working_day"] = ((c.is_weekend == 0) & (c.is_holiday == 0)).astype(int)
    c["is_salary_week"] = c.day_of_month.between(7, 10).astype(int)
    c["is_post_salary_week"] = c.day_of_month.between(11, 16).astype(int)
    c["is_month_end_week"] = (c.days_to_month_end <= 5).astype(int)
    d_f, d_a = (fitr - c.date).dt.days, (adha - c.date).dt.days
    c["days_to_nearest_eid"] = np.where(d_f.abs() <= d_a.abs(), d_f, d_a).clip(-30, 30)
    c["is_pre_eid_fitr"] = d_f.between(3, 9).astype(int)
    c["is_pre_eid_adha"] = d_a.between(3, 9).astype(int)
    c["is_eid_day"] = (d_f.between(-1, 0) | d_a.between(-1, 0)).astype(int)
    c["is_eid_bonus_week"] = (d_f.between(10, 19) | d_a.between(10, 19)).astype(int)
    c["is_ramadan"] = c.date.between(*cfg["ramadan"]).astype(int)
    c["is_semester_start"] = (((c.month == 2) & (c.day_of_month <= 15)) |
                              ((c.month == 7) & (c.day_of_month <= 15))).astype(int)
    wd, n = c.is_working_day.values, len(c)
    closed = np.zeros(n, int)
    for i in range(n):
        k = 1
        while i + k < n and wd[i + k] == 0:
            k += 1
        closed[i] = k - 1 if i + k < n else 0
    c["closed_days_ahead"] = closed
    return c


# ---------------------------------------------------------------- features ---
def _prefix(x):
    return np.concatenate([[0.0], np.cumsum(np.nan_to_num(x))])


def make_features(df, origins=None, h_max=H, min_hist=MIN_HIST):
    """Direct multi-horizon feature builder.

    One output row = one (agent, forecast origin t, horizon h) triple, predicting day d = t + h.
    LEAKAGE RULE: only information available at the END of day t may be used for history
    features (obs[<= t]); calendar features of day d are legitimately known in advance.
    The demand model deliberately ignores the agent's current balances, so it forecasts
    DEMAND, not the agent's own supply decisions. Balances are used later, in the roll-forward.

    df: one row per agent-date (sorted by date), must contain calendar columns for the target dates.
        Future rows (date > origin) may have NaN flows.
    origins: optional set of dates to forecast from; default = every date with enough history
             and a full horizon of future rows.
    """
    rows = []
    origins = None if origins is None else {pd.Timestamp(o) for o in origins}
    for aid, g in df.groupby("agent_id", sort=False):
        g = g.sort_values("date").reset_index(drop=True)
        n = len(g)
        dates = pd.to_datetime(g["date"])
        co, ci = g["observed_cashout"].to_numpy(float), g["observed_cashin"].to_numpy(float)
        tco = g["true_cashout_demand"].to_numpy(float) if "true_cashout_demand" in g else np.full(n, np.nan)
        tci = g["true_cashin_demand"].to_numpy(float) if "true_cashin_demand" in g else np.full(n, np.nan)
        cc = g["closing_cash"].to_numpy(float) if "closing_cash" in g else np.full(n, np.nan)
        ce = g["closing_efloat"].to_numpy(float) if "closing_efloat" in g else np.full(n, np.nan)
        P = {"co": _prefix(co), "ci": _prefix(ci)}
        X = {"co": co, "ci": ci}
        if origins is None:
            t_idx = np.arange(min_hist - 1, n - h_max)
        else:
            t_idx = np.array([i for i in range(n) if dates[i] in origins and i >= min_hist - 1 and i + h_max < n])
        if len(t_idx) == 0:
            continue
        # origin-level quantities
        base = {}
        for p in ("co", "ci"):
            scale = (P[p][t_idx + 1] - P[p][t_idx - 27]) / 28.0
            scale = np.maximum(scale, 1.0)
            base[f"{p}_scale"] = scale
            base[f"{p}_logscale"] = np.log(scale)
            base[f"{p}_last_r"] = X[p][t_idx] / scale
            base[f"{p}_roll7_r"] = ((P[p][t_idx + 1] - P[p][t_idx - 6]) / 7.0) / scale
        base["log_co_ci_scale"] = base["co_logscale"] - base["ci_logscale"]
        cal = g[CAL_COLS].to_numpy()
        traits = g.loc[0, TRAIT_COLS].to_numpy(float)
        logcap = np.log(g.loc[0, ["agent_capacity_cash", "agent_capacity_efloat"]].to_numpy(float))
        for h in range(1, h_max + 1):
            d = t_idx + h
            r = {"agent_id": np.repeat(aid, len(t_idx)),
                 "origin_date": dates.values[t_idx], "target_date": dates.values[d], "h": np.full(len(t_idx), h)}
            r.update(base)
            for p in ("co", "ci"):
                s = base[f"{p}_scale"]
                l7, l14, l21 = X[p][d - 7], X[p][d - 14], X[p][d - 21]
                r[f"{p}_lag7_r"], r[f"{p}_lag14_r"], r[f"{p}_lag21_r"] = l7 / s, l14 / s, l21 / s
                r[f"{p}_dowmean_r"] = np.nanmean(np.stack([l7, l14, l21]), axis=0) / s
            for j, name in enumerate(CAL_COLS):
                r[name] = cal[d, j]
            for j, name in enumerate(TRAIT_COLS):
                r[name] = np.full(len(t_idx), traits[j])
            r["logcap_cash"], r["logcap_ef"] = np.full(len(t_idx), logcap[0]), np.full(len(t_idx), logcap[1])
            r["pre_eid_any"] = ((r["is_pre_eid_fitr"] + r["is_pre_eid_adha"]) > 0).astype(int)
            for e in CROSS_EVENTS:
                for j, tname in enumerate(TRAIT_COLS):
                    r[f"x_{tname}_{e}"] = traits[j] * r[e]
            # targets (NaN at serving time)
            r["y_co"], r["y_ci"], r["yt_co"], r["yt_ci"] = co[d], ci[d], tco[d], tci[d]
            # state at origin (used by the roll-forward, not by the demand model)
            r["cash0"], r["ef0"] = cc[t_idx], ce[t_idx]
            r["closed_ahead_origin"] = g["closed_days_ahead"].to_numpy()[t_idx]
            r["cap_cash"], r["cap_ef"] = np.full(len(t_idx), np.exp(logcap[0])), np.full(len(t_idx), np.exp(logcap[1]))
            rows.append(pd.DataFrame(r))
    return pd.concat(rows, ignore_index=True) if rows else pd.DataFrame()


BASE_FEATURE_COLS = (["h"] + CAL_COLS + TRAIT_COLS + ["logcap_cash", "logcap_ef", "log_co_ci_scale"] +
                     [f"{p}_{s}" for p in ("co", "ci")
                      for s in ("logscale", "last_r", "roll7_r", "lag7_r", "lag14_r", "lag21_r", "dowmean_r")])
FEATURE_COLS = BASE_FEATURE_COLS + CROSS_COLS


# -------------------------------------------------------------- prediction ---
def predict_quantiles(bundle, feats):
    """Returns {'co': (N, n_q), 'ci': (N, n_q)} in currency units (BDT), non-crossing, >= 0."""
    out = {}
    cols = bundle["feature_cols"]
    for flow in ("co", "ci"):
        P = np.column_stack([bundle["models"][flow][q].predict(feats[cols]) for q in bundle["quantiles"]])
        P = np.sort(P, axis=1) * feats[f"{flow}_scale"].to_numpy()[:, None]
        out[flow] = np.maximum(P, 0.0)
    return out


# --------------------------------------------------------- Monte Carlo risk ---
def _inverse_cdf(qs, q_levels, u):
    """Piecewise-linear inverse CDF through the predicted quantiles.
    Tails beyond q10/q90 are extrapolated (assumption, documented in the notebook)."""
    lo = max(0.0, qs[0] - 0.75 * (qs[2] - qs[0]))
    hi = qs[-1] + 0.75 * (qs[-1] - qs[2])
    return np.interp(u, np.concatenate([[0.0], q_levels, [1.0]]), np.concatenate([[lo], qs, [hi]]))


def sample_flows(q_co, q_ci, q_levels, n_paths, rng):
    """q_co, q_ci: (H, n_q) quantile forecasts for one agent at one origin.
    Days and flows are sampled independently (simplifying assumption)."""
    Hh = q_co.shape[0]
    co = np.column_stack([_inverse_cdf(q_co[k], q_levels, rng.random(n_paths)) for k in range(Hh)])
    ci = np.column_stack([_inverse_cdf(q_ci[k], q_levels, rng.random(n_paths)) for k in range(Hh)])
    return co, ci


def risk_summary(q_co, q_ci, q_levels, cash0, ef0, cap_cash, cap_ef, closed_ahead, scale_co, scale_ci,
                 cfg=None, rng=None, extra_coverage=()):
    """Turns the demand distribution into the five app outputs for one agent at one origin."""
    cfg = {**DEFAULT_RISK_CONFIG, **(cfg or {})}
    rng = rng or np.random.default_rng(0)
    co, ci = sample_flows(q_co, q_ci, q_levels, cfg["n_paths"], rng)
    net = co - ci                                   # >0 drains cash, raises e-float
    cum = np.cumsum(net, axis=1)
    buf_c, buf_e = cfg["buffer_frac"] * cap_cash, cfg["buffer_frac"] * cap_ef
    cash_path, ef_path = cash0 - cum, ef0 + cum
    cash_breach = np.maximum.accumulate(cash_path < buf_c, axis=1)   # "has run out by day k"
    ef_breach = np.maximum.accumulate(ef_path < buf_e, axis=1)
    risk_cash_by_day, risk_ef_by_day = cash_breach.mean(0), ef_breach.mean(0)

    def first_day(r):
        idx = np.where(r >= 0.5)[0]
        return int(idx[0]) + 1 if len(idx) else None

    # Output 5: recommended holding level. Window = days until a top-up can realistically arrive
    # (closed days ahead + order lead time), capped at the horizon.
    W = int(min(q_co.shape[0], closed_ahead + 2))
    max_out, max_in = cum[:, :W].max(axis=1), (-cum[:, :W]).max(axis=1)   # worst cumulative drain per path
    req_by_cov = {}
    for p in sorted({cfg["coverage_prob"], *extra_coverage}):
        req_by_cov[p] = (max(np.quantile(max_out, p), 0.0) + buf_c, max(np.quantile(max_in, p), 0.0) + buf_e)
    req_cash, req_ef = req_by_cov[cfg["coverage_prob"]]
    topup_cash, topup_ef = max(0.0, req_cash - cash0), max(0.0, req_ef - ef0)
    total = cash0 + ef0
    return dict(
        cash_risk_pct_7d=100 * risk_cash_by_day[-1], efloat_risk_pct_7d=100 * risk_ef_by_day[-1],       # outputs 1, 2
        cash_risk_pct_by_day=100 * risk_cash_by_day, efloat_risk_pct_by_day=100 * risk_ef_by_day,
        likely_cash_runout_day=first_day(risk_cash_by_day), likely_efloat_runout_day=first_day(risk_ef_by_day),
        cashout_q=q_co, cashin_q=q_ci,                                                                    # outputs 3, 4
        expected_cashout=co.mean(0), expected_cashin=ci.mean(0),
        p_cashout_surge=(co > cfg["surge_multiple"] * scale_co).mean(0),
        p_cashin_surge=(ci > cfg["surge_multiple"] * scale_ci).mean(0),
        coverage_window_days=W, recommended_cash_level=req_cash, recommended_efloat_level=req_ef,         # output 5
        topup_cash_needed=topup_cash if topup_cash >= cfg["min_order_frac"] * cap_cash else 0.0,
        topup_efloat_needed=topup_ef if topup_ef >= cfg["min_order_frac"] * cap_ef else 0.0,
        float_insufficient=bool(req_cash + req_ef > total),
        req_by_coverage=req_by_cov,
    )


# ----------------------------------------------------------- serving helper ---
def get_agent_row(bundle, agent_id):
    """Agent traits + capacities in the shape forecast_agent() expects."""
    a = bundle["agents"].set_index("agent_id").loc[agent_id].copy()
    a["agent_id"] = agent_id
    for c in TRAIT_COLS:
        a[c] = int(a[c])
    return a


def forecast_agent(bundle, history, agent_row, origin_date, closing_cash, closing_efloat, seed=0):
    """Serve-time entry point.
    history   : DataFrame[date, observed_cashout, observed_cashin] with >= 28 days up to origin_date
    agent_row : Series with the agent traits and capacities (see bundle['agents'])
    Builds future calendar rows itself, so no future data is required."""
    origin = pd.Timestamp(origin_date)
    hist = history[history["date"] <= origin].copy()
    hist["date"] = pd.to_datetime(hist["date"])
    fut_dates = [origin + timedelta(i) for i in range(1, H + 1)]
    all_dates = list(hist["date"]) + fut_dates
    cal = build_calendar(all_dates + [origin + timedelta(H + 30)], bundle["calendar_config"]).iloc[:len(all_dates)]
    df = cal.copy()
    df["agent_id"] = agent_row["agent_id"]
    for c in TRAIT_COLS:
        df[c] = agent_row[c]
    df["agent_capacity_cash"], df["agent_capacity_efloat"] = agent_row["capacity_cash"], agent_row["capacity_efloat"]
    df["observed_cashout"] = list(hist["observed_cashout"]) + [np.nan] * H
    df["observed_cashin"] = list(hist["observed_cashin"]) + [np.nan] * H
    df["closing_cash"], df["closing_efloat"] = closing_cash, closing_efloat
    f = make_features(df, origins=[origin])
    if f.empty:
        raise ValueError("Need at least 28 days of history ending at the origin date.")
    q = predict_quantiles(bundle, f)
    r = f.iloc[0]
    return risk_summary(q["co"], q["ci"], bundle["quantiles"], closing_cash, closing_efloat,
                        r["cap_cash"], r["cap_ef"], int(r["closed_ahead_origin"]), r["co_scale"], r["ci_scale"],
                        bundle["risk_config"], np.random.default_rng(seed))


# --------------------------------------------------------------- explanation ---
FEATURE_LABELS = {
    "is_salary_week": "Salary week (7th-10th)", "is_post_salary_week": "Post-salary week (11th-16th)",
    "is_month_end_week": "Month-end week", "days_to_month_end": "Days to month end",
    "day_of_month": "Day of month", "day_of_week": "Day of week", "is_friday": "Friday",
    "is_weekend": "Weekend (Fri/Sat)", "is_holiday": "Public holiday", "is_working_day": "Working day",
    "closed_days_ahead": "Closed days ahead", "is_eid_day": "Eid day", "is_pre_eid_fitr": "Pre-Eid-ul-Fitr shopping window",
    "is_pre_eid_adha": "Pre-Eid-ul-Adha shopping window", "is_eid_bonus_week": "Eid bonus week",
    "days_to_nearest_eid": "Distance to nearest Eid", "is_ramadan": "Ramadan", "is_semester_start": "University semester start",
    "month": "Month of year", "h": "Forecast horizon", "urban": "Urban location", "garment": "Garment area",
    "remittance": "Remittance area", "agri": "Agricultural area", "university": "University area",
    "logcap_cash": "Agent cash capacity", "logcap_ef": "Agent e-float capacity", "log_co_ci_scale": "Cash-out vs cash-in balance",
}
for _p, _n in (("co", "cash-out"), ("ci", "cash-in")):
    FEATURE_LABELS.update({f"{_p}_logscale": f"Typical {_n} level (28d)", f"{_p}_last_r": f"Yesterday's {_n}",
                           f"{_p}_roll7_r": f"Last 7 days' {_n}", f"{_p}_lag7_r": f"{_n.capitalize()} same weekday last week",
                           f"{_p}_lag14_r": f"{_n.capitalize()} same weekday 2 weeks ago",
                           f"{_p}_lag21_r": f"{_n.capitalize()} same weekday 3 weeks ago",
                           f"{_p}_dowmean_r": f"{_n.capitalize()} same-weekday average"})


_TRAIT_NAMES = {"urban": "urban agent", "garment": "garment-area agent", "remittance": "remittance-area agent",
                "agri": "agricultural-area agent", "university": "university-area agent"}
_EVENT_NAMES = {"is_salary_week": "salary week", "is_post_salary_week": "post-salary week", "is_month_end_week": "month-end week",
                "is_eid_bonus_week": "Eid bonus week", "pre_eid_any": "pre-Eid shopping window",
                "is_semester_start": "semester start", "is_ramadan": "Ramadan"}
for _e in CROSS_EVENTS:
    for _t in TRAIT_COLS:
        FEATURE_LABELS[f"x_{_t}_{_e}"] = f"{_TRAIT_NAMES[_t]} x {_EVENT_NAMES[_e]}"


def _is_flag(col):
    return col in CAL_COLS and col.startswith("is_") or col in TRAIT_COLS or col.startswith("x_")


def explain_prediction(bundle, feat_row, flow="co", top=6):
    """Why does the median forecast differ from the agent's typical level?
    Uses LightGBM's exact tree-SHAP contributions (pred_contrib) of the q50 model.
    Returns [(label, contribution_in_BDT)] sorted by absolute size, plus the baseline level."""
    cols = bundle["feature_cols"]
    booster = bundle["models"][flow][0.5]
    contrib = booster.predict(feat_row[cols], pred_contrib=True)[0]
    scale = float(feat_row[f"{flow}_scale"].iloc[0])
    vals = feat_row[cols].iloc[0]

    def fmt(c):
        v = vals[c]
        if _is_flag(c):
            return "yes" if v >= 0.5 else "no"
        return f"{v:,.0f}" if c in ("day_of_month", "day_of_week", "month", "days_to_month_end", "h", "closed_days_ahead",
                                    "days_to_nearest_eid") else f"{v:.2f}"
    pairs = [(f"{FEATURE_LABELS.get(c, c)}: {fmt(c)}", float(v) * scale) for c, v in zip(cols, contrib[:-1])]
    pairs.sort(key=lambda t: -abs(t[1]))
    return pairs[:top], float(contrib[-1]) * scale
