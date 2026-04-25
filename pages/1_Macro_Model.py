# ============================================================
# BLUE EAGLE — MACRO MARKET MODEL PAGE
# pages/1_Macro_Model.py
# ============================================================

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from macro_model import (
    load_macro_data,
    load_cached_macro_data,
    build_macro_signals,
    run_macro_backtest,
    summarize_macro_performance,
)
from theme import get_colors, get_plotly_template

st.set_page_config(
    page_title="Macro Market Model — Blue Eagle",
    page_icon="📊",
    layout="wide",
)

st.title("📊 Macro Market Model")
st.caption("S&P 500 market timing · ISM Manufacturing New Orders · Real M2 Impulse · 10Y Rates · Momentum")
st.divider()

# ------------------------------------------------------------------ sidebar
with st.sidebar:
    st.header("Macro Market Model")
    st.caption("S&P 500 timing — ISM · Real M2 · Rates · Momentum")
    macro_load_btn = st.button("Load Macro Model", type="primary", use_container_width=True)

# ------------------------------------------------------------------ cache
@st.cache_data(show_spinner="Fetching S&P 500 + FRED macro data…")
def cached_load_macro(force_refresh: bool = False):
    return load_macro_data(force_refresh=force_refresh)

# ------------------------------------------------------------------ session state
if "macro_df" not in st.session_state:
    st.session_state["macro_df"]   = None
    st.session_state["macro_bt"]   = None
    st.session_state["macro_perf"] = None

if st.session_state["macro_df"] is None:
    cached_macro = load_cached_macro_data()
    if cached_macro is not None:
        sp_daily, sp_monthly, fred_dict = cached_macro
        macro_df   = build_macro_signals(sp_daily, sp_monthly, fred_dict)
        macro_bt   = run_macro_backtest(macro_df)
        macro_perf = summarize_macro_performance(macro_bt)
        macro_perf["sell_freq"] = (macro_df["signal"] == "SELL").mean()
        st.session_state["macro_df"]   = macro_df
        st.session_state["macro_bt"]   = macro_bt
        st.session_state["macro_perf"] = macro_perf

if macro_load_btn:
    cached_load_macro.clear()
    sp_daily, sp_monthly, fred_dict = cached_load_macro(force_refresh=True)
    macro_df   = build_macro_signals(sp_daily, sp_monthly, fred_dict)
    macro_bt   = run_macro_backtest(macro_df)
    macro_perf = summarize_macro_performance(macro_bt)
    macro_perf["sell_freq"] = (macro_df["signal"] == "SELL").mean()
    st.session_state["macro_df"]   = macro_df
    st.session_state["macro_bt"]   = macro_bt
    st.session_state["macro_perf"] = macro_perf
    st.sidebar.success("Macro model loaded.")

_macro_df   = st.session_state["macro_df"]
_macro_bt   = st.session_state["macro_bt"]
_macro_perf = st.session_state["macro_perf"]

# ------------------------------------------------------------------ content
if _macro_df is None:
    st.info("Click **Load Macro Model** in the sidebar to run the S&P 500 timing model.")
    st.stop()

_latest       = _macro_df.dropna(subset=["macro_score"]).iloc[-1]
_macro_score  = int(_latest["macro_score"])
_macro_regime = _latest["macro_regime"]
_mom_regime   = _latest["momentum_regime"]
_signal_val   = _latest["signal"]
_signal_date  = _latest.name.strftime("%b %Y")

_c = get_colors()
_signal_colors = {"BUY": _c["buy_bg"], "HOLD": _c["hold_bg"], "SELL": _c["sell_bg"]}
_signal_emojis = {"BUY": "🟢", "HOLD": "🟡", "SELL": "🔴"}

# ---- current signal ----
st.subheader(f"Current Signal — {_signal_date}")

_col_sig, _col_votes = st.columns([1, 2])

with _col_sig:
    _bg    = _signal_colors.get(_signal_val, "#1a1d24")
    _emoji = _signal_emojis.get(_signal_val, "⬜")
    st.markdown(
        f"""
        <div style='background:{_bg};border:1px solid #444;padding:24px;
        border-radius:12px;text-align:center;'>
        <div style='font-size:2.2em;font-weight:bold'>{_emoji} {_signal_val}</div>
        <div style='font-size:0.9em;color:#ccc;margin-top:6px'>as of {_signal_date}</div>
        <div style='font-size:0.85em;color:#aaa;margin-top:4px'>
            Macro: <b>{_macro_regime}</b> (score {_macro_score}) &nbsp;|&nbsp;
            Momentum: <b>{_mom_regime}</b>
        </div>
        </div>
        """,
        unsafe_allow_html=True,
    )

with _col_votes:
    _vote_data = {
        "Signal": ["ISM New Orders", "Real M2 Impulse", "10Y Rates"],
        "Vote":   [int(_latest["ism_vote"]), int(_latest["m2_vote"]), int(_latest["rate_vote"])],
        "Value":  [
            f"{_latest['ism']:.1f}" if pd.notna(_latest.get("ism")) else "—",
            f"{_latest['real_m2_impulse']:.2f}pp" if pd.notna(_latest.get("real_m2_impulse")) else "—",
            f"{_latest['rate_signal']:.2f}pp" if pd.notna(_latest.get("rate_signal")) else "—",
        ],
    }
    _vote_df = pd.DataFrame(_vote_data)

    def _vote_color(row):
        v = row["Vote"]
        _c = get_colors()
        if v == 1:
            return ["", _c["green_row"], ""]
        elif v == -1:
            return ["", _c["red_row"], ""]
        else:
            return ["", _c["yellow_row"], ""]

    st.dataframe(
        _vote_df.style.apply(_vote_color, axis=1),
        use_container_width=True,
        hide_index=True,
    )
    st.caption(
        f"Macro Score: **{_macro_score}** → Regime: **{_macro_regime}** "
        "| BUY if score ≥ 2, SELL if score ≤ −1 AND momentum Bearish"
    )

st.divider()

# ---- quadrant chart ----
st.subheader("Macro vs Momentum Quadrant")

_mom_pct = float(_latest["momentum"]) * 100 if pd.notna(_latest.get("momentum")) else 0.0

_fig_quad = go.Figure()
_fig_quad.add_vrect(x0=2,   x1=3.5, fillcolor="#2ca02c", opacity=0.08, line_width=0)
_fig_quad.add_vrect(x0=-1,  x1=2,   fillcolor="#f5c518", opacity=0.05, line_width=0)
_fig_quad.add_shape(type="rect", x0=-2.5, x1=-1, y0=-35, y1=0,
                    fillcolor="#d62728", opacity=0.08, line_width=0)
_fig_quad.add_vline(x=2,  line_dash="dash", line_color="#888", line_width=1)
_fig_quad.add_vline(x=-1, line_dash="dash", line_color="#888", line_width=1)
_fig_quad.add_shape(type="line", x0=-2.5, x1=-1, y0=0, y1=0,
                    line=dict(color="#888", dash="dash", width=1))
for _txt, _x, _y, _clr in [
    ("BUY",  2.75,  25, "#2ca02c"),
    ("HOLD", 0.5,   25, "#f5c518"),
    ("HOLD", -1.75, 20, "#f5c518"),
    ("SELL", -1.75, -20, "#d62728"),
]:
    _fig_quad.add_annotation(text=_txt, x=_x, y=_y, showarrow=False,
                              font=dict(size=14, color=_clr), opacity=0.6)
_fig_quad.add_trace(go.Scatter(
    x=[_macro_score], y=[_mom_pct],
    mode="markers+text",
    marker=dict(size=16, color="#1f77b4", line=dict(color="white", width=2)),
    text=[f"  {_signal_date}: {_signal_val}"],
    textposition="middle right",
    textfont=dict(color="white", size=11),
    showlegend=False,
))
_fig_quad.update_layout(
    xaxis=dict(title="Macro Score", range=[-2.5, 3.5], tickvals=list(range(-2, 4))),
    yaxis=dict(title="Momentum (%)", range=[-35, 35], tickformat=".0f", ticksuffix="%"),
    template=get_plotly_template(),
    height=380,
    margin=dict(l=0, r=0, t=20, b=0),
)
st.plotly_chart(_fig_quad, use_container_width=True)

st.divider()

# ---- backtest performance ----
st.subheader("Macro Model Backtest Performance")

_col_m1, _col_m2 = st.columns([1, 2])

with _col_m1:
    _perf_rows = [
        ("CAGR",         _macro_perf["cagr_strategy"],  _macro_perf["cagr_buyhold"],  True),
        ("Sharpe Ratio", _macro_perf["sharpe_strategy"], _macro_perf["sharpe_buyhold"], False),
        ("Max Drawdown", _macro_perf["maxdd_strategy"],  _macro_perf["maxdd_buyhold"],  True),
    ]
    for _lbl, _strat, _bench, _is_pct in _perf_rows:
        _fmt = (lambda v: f"{v:.2%}") if _is_pct else (lambda v: f"{v:.2f}")
        st.metric(
            label=_lbl,
            value=_fmt(_strat) if pd.notna(_strat) else "—",
            delta=f"B&H: {_fmt(_bench)}" if pd.notna(_bench) else "—",
        )
    st.metric("SELL Frequency", f"{_macro_perf.get('sell_freq', 0):.1%}")

with _col_m2:
    _fig_mm = go.Figure()
    _fig_mm.add_trace(go.Scatter(
        x=_macro_bt.index, y=_macro_bt["strategy_cum"],
        mode="lines", name="Macro + Momentum Model",
        line=dict(color="#1f77b4", width=2),
    ))
    _fig_mm.add_trace(go.Scatter(
        x=_macro_bt.index, y=_macro_bt["buyhold_cum"],
        mode="lines", name="S&P 500 Buy & Hold",
        line=dict(color="#ff7f0e", width=1.5, dash="dot"),
    ))
    _in_sell, _sell_start = False, None
    for _dt, _is_sell in (_macro_df["signal"] == "SELL").items():
        if _is_sell and not _in_sell:
            _sell_start, _in_sell = _dt, True
        elif not _is_sell and _in_sell:
            _fig_mm.add_vrect(x0=_sell_start, x1=_dt,
                               fillcolor="#d62728", opacity=0.12, line_width=0)
            _in_sell = False
    if _in_sell:
        _fig_mm.add_vrect(x0=_sell_start, x1=_macro_df.index[-1],
                           fillcolor="#d62728", opacity=0.12, line_width=0)
    _fig_mm.update_layout(
        title="Growth of $1 — Macro + Momentum vs Buy & Hold (red shading = SELL)",
        xaxis_title="Date", yaxis_title="Growth of $1",
        template=get_plotly_template(), height=380,
        margin=dict(l=0, r=0, t=40, b=40),
        legend=dict(orientation="h", yanchor="top", y=-0.15),
    )
    st.plotly_chart(_fig_mm, use_container_width=True)
    st.caption("Benchmark logic: S&P 500 buy-and-hold, using the raw monthly return of the index with no timing filter.")
