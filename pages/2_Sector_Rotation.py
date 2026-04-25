# ============================================================
# BLUE EAGLE — SECTOR ROTATION MODEL PAGE
# pages/2_Sector_Rotation.py
# ============================================================

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import streamlit as st

from config import (
    DEFAULT_LOOKBACK_MONTHS,
    DEFAULT_SKIP_MONTHS,
    DEFAULT_TOP_N,
    DEFAULT_BOTTOM_N,
    USE_MACRO_OVERLAY,
    SAVE_CSV_OUTPUTS,
    GICS_MAP,
)
from signals import build_signals, label_macro_regime
from backtest import run_backtest, summarize_performance
import signals as _signals_module
from theme import get_colors, get_plotly_template

st.set_page_config(
    page_title="Sector Rotation — Blue Eagle",
    page_icon="🔄",
    layout="wide",
)

st.title("🔄 Sector Rotation Model")
st.caption("Momentum + analyst recommendation sector rotation | WRDS · CRSP · Compustat · IBES · FRED")
st.info(
    "Signals are monthly. The displayed signal is computed using the most recent completed "
    "month-end data, then applied to the current month holding period. For example, if today "
    "is mid-April and the latest complete monthly data is March 31, the March 31 signal is the "
    "portfolio guidance for April, not a real-time daily update."
)
st.caption(
    "Base model score = 70% sector momentum + 30% analyst recommendation momentum. "
    "The macro overlay below is optional and acts as an additive tilt on top of that base score."
)
st.divider()

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("WRDS Credentials")
    _default_user = st.secrets.get("wrds", {}).get("username", "")
    _default_pass = st.secrets.get("wrds", {}).get("password", "")
    wrds_username = st.text_input("Username", value=_default_user, key="wrds_user")
    wrds_password = st.text_input("Password", value=_default_pass, type="password", key="wrds_pass")
    load_btn = st.button("Load Data", type="primary", use_container_width=True)
    clear_btn = st.button("Clear Cache", use_container_width=True, help="Delete local disk cache and force a fresh WRDS query")

    st.divider()
    st.header("Model Controls")

    _today = pd.Timestamp.today().normalize()
    _last_month_end = _today.replace(day=1) - pd.Timedelta(days=1)
    start_date = st.date_input("Start date", value=pd.to_datetime("2010-01-01"))
    end_date   = st.date_input("End date",   value=_last_month_end)

    lookback_months = st.slider("Lookback months", 3, 12, DEFAULT_LOOKBACK_MONTHS)
    skip_months     = st.slider("Skip months",      0,  2, DEFAULT_SKIP_MONTHS)
    top_n           = st.slider("Top N (buy)",       1,  5, DEFAULT_TOP_N)
    bottom_n        = st.slider("Bottom N (sell)",   1,  5, DEFAULT_BOTTOM_N)
    use_macro       = st.checkbox("Macro overlay (optional 10Y-2Y tilt)", value=USE_MACRO_OVERLAY)

    st.divider()
    run_btn = st.button("Run Dashboard", type="primary", use_container_width=True)

# ------------------------------------------------------------------ data cache
@st.cache_data(show_spinner=False)
def cached_load_data(username: str, password: str, end_date_key: str, force_refresh: bool = False):
    from data import load_data
    return load_data(username, password, force_refresh=force_refresh)

# ------------------------------------------------------------------ session state
if "sector_returns" not in st.session_state:
    st.session_state["sector_returns"] = None
    st.session_state["fred"]           = pd.DataFrame()
    st.session_state["all_sectors"]    = list(GICS_MAP.values())

if st.session_state["sector_returns"] is None:
    from data import load_cached_data
    _cached_sector = load_cached_data(wrds_username or None)
    if _cached_sector is None and _default_user:
        _cached_sector = load_cached_data(_default_user)
    if _cached_sector is not None:
        sector_returns, fred, all_sectors = _cached_sector
        if not fred.empty:
            fred["macro_regime"] = fred["yield_spread_10y_2y"].apply(label_macro_regime)
        st.session_state["sector_returns"] = sector_returns
        st.session_state["fred"]           = fred
        st.session_state["all_sectors"]    = all_sectors

if "clear_btn" in dir() and clear_btn:
    from data import clear_cache
    clear_cache(wrds_username or None)
    cached_load_data.clear()
    st.session_state.pop("sector_returns", None)
    st.sidebar.success("Cache cleared. Click Load Data to re-query.")

if load_btn:
    if not wrds_username or not wrds_password:
        st.sidebar.error("Enter both username and password.")
    else:
        status_box = st.status("Loading data…", expanded=True)
        def _update_status(msg):
            status_box.update(label=msg)
            status_box.write(msg)

        _update_status("Refreshing from WRDS + FRED and updating local cache. This may take 3-5 minutes…")

        from config import END_DATE as _end_date_key
        cached_load_data.clear()
        sector_returns, fred, all_sectors = cached_load_data(
            wrds_username,
            wrds_password,
            _end_date_key,
            force_refresh=True,
        )
        status_box.update(label="Data loaded.", state="complete", expanded=False)

        if not fred.empty:
            fred["macro_regime"] = fred["yield_spread_10y_2y"].apply(label_macro_regime)
        st.session_state["sector_returns"] = sector_returns
        st.session_state["fred"]           = fred
        st.session_state["all_sectors"]    = all_sectors
        st.session_state.pop("signals", None)
        st.session_state.pop("backtest", None)
        st.sidebar.success("Data loaded.")

sector_returns = st.session_state["sector_returns"]
fred           = st.session_state["fred"]
all_sectors    = st.session_state["all_sectors"]

# Wire globals that build_signals reads
_signals_module.fred = fred

# ------------------------------------------------------------------ no data yet
if sector_returns is None:
    st.info(
        "Enter your WRDS credentials in the sidebar and click **Load Data** to begin. "
        "The first load queries CRSP + Compustat + FRED and may take a few minutes; "
        "results are cached for the session."
    )
    st.stop()

# ------------------------------------------------------------------ build signals
if not run_btn and "signals" not in st.session_state:
    run_btn = True   # auto-run once after data loads

_needs_signal_refresh = False
if "signals" in st.session_state:
    _sig_existing = st.session_state["signals"]
    if not isinstance(_sig_existing, pd.DataFrame):
        _needs_signal_refresh = True
    else:
        required_cols = {"analyst_raw", "analyst_z", "final_score"}
        if not required_cols.issubset(set(_sig_existing.columns)):
            _needs_signal_refresh = True
if "backtest" not in st.session_state:
    _needs_signal_refresh = True

if run_btn or _needs_signal_refresh:
    with st.spinner("Computing signals and backtest…"):
        sig = build_signals(
            sector_returns,
            lookback_months=lookback_months,
            skip_months=skip_months,
            top_n=top_n,
            bottom_n=bottom_n,
            use_macro_overlay=use_macro,
        )
        bt  = run_backtest(sig, top_n=top_n)
        st.session_state["signals"] = sig
        st.session_state["backtest"] = bt

sig = st.session_state["signals"]
bt  = st.session_state["backtest"]

# ------------------------------------------------------------------ filter date range
start_ts = pd.to_datetime(start_date) + pd.offsets.MonthEnd(0)
end_ts   = pd.to_datetime(end_date)   + pd.offsets.MonthEnd(0)

sig_f = sig[(sig["date"] >= start_ts) & (sig["date"] <= end_ts)].copy()
bt_f  = bt[ (bt["date"]  >= start_ts) & (bt["date"]  <= end_ts)].copy()

if sig_f.empty or bt_f.empty:
    st.warning("No data in selected date range.")
    st.stop()

# rebase cumulative to selected window
bt_f["strategy_cum"]  = (1 + bt_f["strategy_ret"].fillna(0)).cumprod()
bt_f["benchmark_cum"] = (1 + bt_f["benchmark_ret"].fillna(0)).cumprod()
bt_f["spread_cum"]    = (1 + bt_f["spread_ret"].fillna(0)).cumprod()

# ------------------------------------------------------------------ current snapshot
current_date = sig_f["date"].max()
current = sig_f[sig_f["date"] == current_date].sort_values("rank").copy()
holding_period_label = (current_date + pd.offsets.MonthBegin(1)).strftime("%B %Y")
signal_as_of_label = current_date.strftime("%Y-%m-%d")

# ================================================================== SECTION 1 — signal cards
st.subheader(f"Current Signal — {signal_as_of_label}")
st.caption(f"Applied to holding period: **{holding_period_label}**")

_c = get_colors()
_green_secs  = current[current["signal"] == "Green"]["sector"].tolist()
_yellow_secs = current[current["signal"] == "Yellow"]["sector"].tolist()
_red_secs    = current[current["signal"] == "Red"]["sector"].tolist()

_card_col1, _card_col2, _card_col3 = st.columns(3)

def _sector_list_html(sectors: list[str]) -> str:
    if not sectors:
        return "<div style='color:#888;font-size:0.85em;margin-top:6px'>—</div>"
    return "".join(
        f"<div style='font-size:0.88em;margin-top:4px'>• {s}</div>" for s in sectors
    )

with _card_col1:
    st.markdown(
        f"""
        <div style='background:{_c["buy_bg"]};border:1px solid #444;padding:18px;
        border-radius:12px;text-align:center;'>
        <div style='font-size:1.6em;font-weight:bold'>🟢 BUY</div>
        <div style='font-size:0.8em;color:#ccc;margin-top:4px'>{len(_green_secs)} sector(s)</div>
        {_sector_list_html(_green_secs)}
        </div>
        """,
        unsafe_allow_html=True,
    )

with _card_col2:
    st.markdown(
        f"""
        <div style='background:{_c["hold_bg"]};border:1px solid #444;padding:18px;
        border-radius:12px;text-align:center;'>
        <div style='font-size:1.6em;font-weight:bold'>🟡 HOLD</div>
        <div style='font-size:0.8em;color:#ccc;margin-top:4px'>{len(_yellow_secs)} sector(s)</div>
        {_sector_list_html(_yellow_secs)}
        </div>
        """,
        unsafe_allow_html=True,
    )

with _card_col3:
    st.markdown(
        f"""
        <div style='background:{_c["sell_bg"]};border:1px solid #444;padding:18px;
        border-radius:12px;text-align:center;'>
        <div style='font-size:1.6em;font-weight:bold'>🔴 SELL</div>
        <div style='font-size:0.8em;color:#ccc;margin-top:4px'>{len(_red_secs)} sector(s)</div>
        {_sector_list_html(_red_secs)}
        </div>
        """,
        unsafe_allow_html=True,
    )

st.divider()

# ================================================================== SECTION 2
st.subheader("Current Month Signal Table")

_base_cols = ["sector", "momentum_raw", "momentum_z", "analyst_raw", "analyst_z"]
_tail_cols = ["macro_adjustment", "final_score", "rank", "signal", "n_stocks"]
show_cols = _base_cols + _tail_cols

# Keep only columns that actually exist in the DataFrame
show_cols = [c for c in show_cols if c in current.columns]

tbl = current[show_cols].copy().reset_index(drop=True)

for c in ["momentum_raw", "momentum_z", "analyst_raw", "analyst_z", "macro_adjustment", "final_score"]:
    if c in tbl.columns:
        tbl[c] = tbl[c].round(4)
tbl["rank"] = tbl["rank"].astype("Int64")

def _row_color(row):
    _c = get_colors()
    c = {"Green": _c["green_row"], "Yellow": _c["yellow_row"], "Red": _c["red_row"]}
    return [c.get(row["signal"], "")] * len(row)

st.dataframe(
    tbl.style.apply(_row_color, axis=1),
    use_container_width=True,
    hide_index=True,
)
st.caption("Columns shown: momentum factor, analyst factor, optional macro adjustment, and final combined score.")

st.divider()

# ================================================================== SECTION 3
st.subheader("Backtest Performance Summary")

perf = summarize_performance(bt_f)

col1, col2 = st.columns([1, 2])

with col1:
    for _, row in perf.iterrows():
        metric = row["Metric"]
        strat  = row["Strategy"]
        bench  = row["Benchmark"]
        spread = row["Green-Red Spread"]
        if metric == "Sharpe Ratio":
            fmt = lambda v: f"{v:.2f}" if pd.notna(v) else "—"
        else:
            fmt = lambda v: f"{v:.2%}" if pd.notna(v) else "—"
        st.metric(
            label=metric,
            value=fmt(strat),
            delta=f"Bench: {fmt(bench)} | Spread: {fmt(spread)}",
        )

with col2:
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=bt_f["date"], y=bt_f["strategy_cum"],  mode="lines", name="Strategy",        line=dict(color="#1f77b4", width=2)))
    fig1.add_trace(go.Scatter(x=bt_f["date"], y=bt_f["benchmark_cum"], mode="lines", name="Benchmark",       line=dict(color="#aaa",    width=1.5, dash="dot")))
    fig1.add_trace(go.Scatter(x=bt_f["date"], y=bt_f["spread_cum"],    mode="lines", name="Green-Red Spread", line=dict(color="#2ca02c", width=1.5)))
    fig1.update_layout(
        title="Cumulative Performance (Growth of $1)",
        xaxis_title="Date",
        yaxis_title="Growth of $1",
        template=get_plotly_template(),
        height=380,
        margin=dict(l=0, r=0, t=40, b=40),
        legend=dict(orientation="h", yanchor="top", y=-0.15),
    )
    st.plotly_chart(fig1, use_container_width=True)
    st.caption(
        "Benchmark logic: equal-weight average of all sector next-month returns. "
        "Spread logic: Green basket average return minus Red basket average return."
    )

# ================================================================== SECTION 4
st.subheader("Momentum Bar Chart")

fig3 = px.bar(
    current.sort_values("rank"),
    x="sector",
    y="momentum_raw",
    color="signal",
    color_discrete_map={"Green": "#2ca02c", "Yellow": "#f5c518", "Red": "#d62728"},
    title=f"Sector Momentum ({current_date.date()})",
    hover_data=["rank", "final_score", "n_stocks"],
    labels={"momentum_raw": "Momentum (compound return)", "sector": "Sector"},
)
fig3.update_layout(template=get_plotly_template(), height=420, margin=dict(l=0, r=0, t=40, b=0))
st.plotly_chart(fig3, use_container_width=True)

st.divider()

# ================================================================== SECTION 5
st.subheader("Traffic Light Heatmap")

signal_to_num = {"Red": -1, "Yellow": 0, "Green": 1}
hm = sig_f[["date", "sector", "signal"]].copy()
hm["signal_num"] = hm["signal"].map(signal_to_num)
heat = hm.pivot(index="sector", columns="date", values="signal_num").reindex(all_sectors)

fig2 = px.imshow(
    heat,
    aspect="auto",
    title="Traffic Light Heatmap (Green=1, Yellow=0, Red=−1)",
    color_continuous_scale=["#d62728", "#f5c518", "#2ca02c"],
    zmin=-1,
    zmax=1,
)
fig2.update_layout(template=get_plotly_template(), height=480, margin=dict(l=0, r=0, t=40, b=0))
st.plotly_chart(fig2, use_container_width=True)

st.divider()

# ================================================================== SECTION 7
st.subheader("Full Signal History")

with st.expander("Show full signal table"):
    _h_base = ["date", "sector", "sector_ret", "momentum_raw", "momentum_z"]
    _h_analyst = ["analyst_raw", "analyst_z"] if "analyst_raw" in sig_f.columns else []
    _h_tail = ["macro_adjustment", "final_score", "rank", "signal", "n_stocks"]
    hist_cols = [c for c in _h_base + _h_analyst + _h_tail if c in sig_f.columns]

    hist = sig_f[hist_cols].copy()
    for c in ["sector_ret", "momentum_raw", "momentum_z", "analyst_raw", "analyst_z",
              "macro_adjustment", "final_score"]:
        if c in hist.columns:
            hist[c] = hist[c].round(4)
    st.dataframe(hist.reset_index(drop=True), use_container_width=True, hide_index=True)

    if SAVE_CSV_OUTPUTS:
        st.download_button(
            "Download signals CSV",
            data=hist.to_csv(index=False).encode(),
            file_name="sector_signals.csv",
            mime="text/csv",
        )
        bt_dl = bt_f.copy()
        st.download_button(
            "Download backtest CSV",
            data=bt_dl.to_csv(index=False).encode(),
            file_name="sector_backtest.csv",
            mime="text/csv",
        )
