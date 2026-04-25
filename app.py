# ============================================================
# BLUE EAGLE SECTOR ROTATION DASHBOARD
# app.py — Home / Overview page
# ============================================================

import streamlit as st
import numpy as np
import pandas as pd
import plotly.graph_objects as go

import signals as _signals_module
from backtest import run_backtest
from config import (
    DEFAULT_LOOKBACK_MONTHS,
    DEFAULT_SKIP_MONTHS,
    DEFAULT_TOP_N,
    DEFAULT_BOTTOM_N,
    DEFENSIVES,
    USE_MACRO_OVERLAY,
)
from data import load_cached_data
from macro_model import (
    MACRO_START_DATE,
    build_macro_signals,
    load_cached_macro_data,
    run_macro_backtest,
)
from signals import build_signals, label_macro_regime
from theme import get_colors, get_plotly_template
from utils import annualized_return, annualized_vol, sharpe_ratio, max_drawdown

st.set_page_config(
    page_title="Blue Eagle Capital",
    page_icon="🦅",
    layout="wide",
)


def build_backtest_chart(title: str,
                         history_start: pd.Timestamp,
                         backtest_end: pd.Timestamp,
                         signal_as_of: pd.Timestamp = None,
                         line_x=None,
                         line_y=None) -> go.Figure:
    if line_x is not None and line_y is not None and len(line_x) > 1 and len(line_y) > 1:
        x = pd.to_datetime(pd.Index(line_x))
        y = pd.Series(line_y, index=x)
        yaxis_title = "Growth of $1"
        line_name = "Strategy cumulative return"
    else:
        x = pd.date_range(history_start, backtest_end, freq="ME")
        y = 1 + 0.18 * pd.Series(range(len(x)), index=x) / max(len(x) - 1, 1)
        yaxis_title = "Illustrative index"
        line_name = "Illustrative timeline"

    fig = go.Figure()
    fig.add_vrect(x0=history_start, x1=backtest_end, fillcolor="#1f77b4", opacity=0.08, line_width=0)
    if signal_as_of is not None:
        fig.add_vline(x=signal_as_of, line_dash="dash", line_color="#bbbbbb", line_width=1.5)
        y_annot = float(y.loc[signal_as_of]) if signal_as_of in y.index else float(y.iloc[-1])
        fig.add_annotation(
            x=signal_as_of, y=y_annot,
            text=f"Signal as of<br>{signal_as_of.strftime('%Y-%m-%d')}",
            showarrow=True, arrowhead=2, ax=-60, ay=-36,
            bgcolor="rgba(0,0,0,0.30)", bordercolor="#888",
        )
    fig.add_trace(go.Scatter(x=x, y=y, mode="lines", line=dict(color="#1f77b4", width=2), name=line_name, showlegend=False))
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title=yaxis_title,
        template=get_plotly_template(),
        height=280,
        margin=dict(l=0, r=0, t=40, b=10),
        yaxis=dict(showticklabels=line_x is not None and line_y is not None),
        xaxis=dict(range=[history_start, backtest_end]),
    )
    return fig


def build_signal_chart(title: str,
                       signal_as_of: pd.Timestamp,
                       signal_start: pd.Timestamp,
                       signal_end: pd.Timestamp,
                       applied_start: pd.Timestamp,
                       applied_end: pd.Timestamp,
                       line_x=None,
                       line_y=None) -> go.Figure:
    x_start = signal_start - pd.DateOffset(months=1)
    x_end = applied_end + pd.DateOffset(months=1)

    if line_x is not None and line_y is not None and len(line_x) > 1:
        x = pd.to_datetime(pd.Index(line_x))
        y = pd.Series(line_y, index=x)
        mask = (x >= x_start) & (x <= x_end)
        x_plot, y_plot = x[mask], y[mask]
        yaxis_title = "Growth of $1"
    else:
        x_plot = pd.date_range(x_start, x_end, freq="ME")
        y_plot = pd.Series([1.0] * len(x_plot), index=x_plot)
        yaxis_title = ""

    fig = go.Figure()
    fig.add_vrect(x0=signal_start, x1=signal_end, fillcolor="#f5c518", opacity=0.18, line_width=0)
    fig.add_vrect(x0=applied_start, x1=applied_end, fillcolor="#2ca02c", opacity=0.10, line_width=0)
    fig.add_trace(go.Scatter(x=x_plot, y=y_plot, mode="lines", line=dict(color="#1f77b4", width=2), showlegend=False))
    fig.add_vline(x=signal_as_of, line_dash="dash", line_color="#bbbbbb", line_width=1.5)
    y_annot = float(y_plot.loc[signal_as_of]) if signal_as_of in y_plot.index else float(y_plot.iloc[-1])
    fig.add_annotation(
        x=signal_as_of, y=y_annot,
        text=f"Signal formed<br>{signal_as_of.strftime('%Y-%m-%d')}",
        showarrow=True, arrowhead=2, ax=36, ay=-36,
        bgcolor="rgba(0,0,0,0.30)", bordercolor="#888",
    )
    # legend
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(size=10, color="#f5c518", opacity=0.6, symbol="square"), name="Signal window"))
    fig.add_trace(go.Scatter(x=[None], y=[None], mode="markers", marker=dict(size=10, color="#2ca02c", opacity=0.4, symbol="square"), name="Applied month"))
    fig.update_layout(
        title=title,
        xaxis_title="Time",
        yaxis_title=yaxis_title,
        template=get_plotly_template(),
        height=220,
        margin=dict(l=0, r=0, t=40, b=40),
        yaxis=dict(showticklabels=line_x is not None and line_y is not None),
        xaxis=dict(range=[x_start, x_end]),
        legend=dict(orientation="h", yanchor="top", y=-0.2, xanchor="left", x=0, font=dict(size=11)),
    )
    return fig


def build_aggregate_backtest(macro_df: pd.DataFrame | None,
                             sector_sig: pd.DataFrame | None,
                             top_n: int,
                             holding_months: int = 3,
                             sell_mode: str = "defensive") -> pd.DataFrame:
    if macro_df is None or sector_sig is None or macro_df.empty or sector_sig.empty:
        return pd.DataFrame()

    macro_signals = macro_df[["signal"]].copy()
    macro_signals.index = pd.to_datetime(macro_signals.index)
    macro_signals = macro_signals.reset_index(names="signal_date")

    selected_top = (
        sector_sig.dropna(subset=["rank", "sector_ret"])
        .loc[lambda df: df["rank"] <= top_n, ["date", "sector"]]
        .rename(columns={"date": "signal_date"})
        .copy()
    )
    selected_top["signal_date"] = pd.to_datetime(selected_top["signal_date"])

    selected_defensive = (
        sector_sig.dropna(subset=["sector_ret"])
        .loc[lambda df: df["sector"].isin(DEFENSIVES), ["date", "sector"]]
        .rename(columns={"date": "signal_date"})
        .copy()
    )
    selected_defensive["signal_date"] = pd.to_datetime(selected_defensive["signal_date"])

    if selected_top.empty:
        return pd.DataFrame()

    sector_returns = (
        sector_sig.dropna(subset=["sector_ret"])[["date", "sector", "sector_ret"]]
        .rename(columns={"date": "holding_date"})
        .copy()
    )
    sector_returns["holding_date"] = pd.to_datetime(sector_returns["holding_date"])

    top_vintages = []
    defensive_vintages = []
    for month_offset in range(1, holding_months + 1):
        top_leg = selected_top.copy()
        top_leg["holding_date"] = top_leg["signal_date"] + pd.offsets.MonthEnd(month_offset)
        top_leg["holding_month"] = month_offset
        top_vintages.append(top_leg)

        defensive_leg = selected_defensive.copy()
        defensive_leg["holding_date"] = defensive_leg["signal_date"] + pd.offsets.MonthEnd(month_offset)
        defensive_leg["holding_month"] = month_offset
        defensive_vintages.append(defensive_leg)

    top_overlap = pd.concat(top_vintages, ignore_index=True)
    top_overlap = top_overlap.merge(
        sector_returns,
        on=["holding_date", "sector"],
        how="left",
    )
    top_overlap = top_overlap.merge(macro_signals, on="signal_date", how="left")
    top_overlap = top_overlap.dropna(subset=["sector_ret", "signal"]).copy()

    defensive_overlap = pd.concat(defensive_vintages, ignore_index=True)
    defensive_overlap = defensive_overlap.merge(
        sector_returns,
        on=["holding_date", "sector"],
        how="left",
    )
    defensive_overlap = defensive_overlap.dropna(subset=["sector_ret"]).copy()

    if top_overlap.empty:
        return pd.DataFrame()

    top_ret = (
        top_overlap.groupby(["signal_date", "holding_date"], as_index=False)
        .agg(
            top_basket_ret=("sector_ret", "mean"),
            macro_signal=("signal", "first"),
            holding_month=("holding_month", "first"),
        )
    )
    defensive_ret = (
        defensive_overlap.groupby(["signal_date", "holding_date"], as_index=False)
        .agg(defensive_basket_ret=("sector_ret", "mean"))
    )
    vintage_ret = top_ret.merge(defensive_ret, on=["signal_date", "holding_date"], how="left")
    vintage_ret["benchmark_ret"] = vintage_ret["top_basket_ret"]

    if sell_mode == "cash":
        vintage_ret["strategy_ret"] = np.where(
            vintage_ret["macro_signal"].isin(["BUY", "HOLD"]),
            vintage_ret["top_basket_ret"],
            0.0,
        )
    elif sell_mode == "short":
        vintage_ret["strategy_ret"] = np.where(
            vintage_ret["macro_signal"].isin(["BUY", "HOLD"]),
            vintage_ret["top_basket_ret"],
            -vintage_ret["top_basket_ret"],
        )
    elif sell_mode == "defensive":
        vintage_ret["strategy_ret"] = np.where(
            vintage_ret["macro_signal"].isin(["BUY", "HOLD"]),
            vintage_ret["top_basket_ret"],
            vintage_ret["defensive_basket_ret"].fillna(0.0),
        )
    else:
        raise ValueError(f"Unsupported sell_mode: {sell_mode}")

    vintage_ret["position"] = np.where(
        vintage_ret["macro_signal"].isin(["BUY", "HOLD"]),
        1.0,
        np.where(vintage_ret["strategy_ret"].eq(0.0), 0.0, 1.0),
    )

    portfolio = (
        vintage_ret.groupby("holding_date", as_index=False)
        .agg(
            strategy_ret=("strategy_ret", "mean"),
            benchmark_ret=("benchmark_ret", "mean"),
            active_vintages=("signal_date", "nunique"),
            avg_position=("position", "mean"),
        )
        .rename(columns={"holding_date": "date"})
        .sort_values("date")
        .reset_index(drop=True)
    )
    portfolio["strategy_cum"] = (1 + portfolio["strategy_ret"]).cumprod()
    portfolio["benchmark_cum"] = (1 + portfolio["benchmark_ret"]).cumprod()
    return portfolio


def summarize_aggregate_performance(bt: pd.DataFrame) -> pd.DataFrame:
    if bt.empty:
        return pd.DataFrame()

    return pd.DataFrame({
        "Metric": [
            "Annualized Return",
            "Annualized Volatility",
            "Sharpe Ratio",
            "Max Drawdown",
        ],
        "Aggregate Strategy": [
            annualized_return(bt["strategy_ret"]),
            annualized_vol(bt["strategy_ret"]),
            sharpe_ratio(bt["strategy_ret"]),
            max_drawdown(bt["strategy_ret"]),
        ],
        "Aggregate Benchmark": [
            annualized_return(bt["benchmark_ret"]),
            annualized_vol(bt["benchmark_ret"]),
            sharpe_ratio(bt["benchmark_ret"]),
            max_drawdown(bt["benchmark_ret"]),
        ],
    })

st.title("🦅 Blue Eagle Capital — Macro & Sector Rotation")
st.caption("Top-down equity allocation | Macro timing · Sector momentum + analyst revisions | WRDS · CRSP · Compustat · IBES · FRED")
st.divider()

col1, col2 = st.columns(2)

with col1:
    st.subheader("📊 Macro Market Model")
    st.markdown(
        """
        S&P 500 market-timing model combining:
        - **ISM Manufacturing New Orders** — economic cycle indicator
        - **Real M2 Impulse** — liquidity conditions
        - **10Y Treasury Rates** — rate trend signal
        - **Price Momentum** — trend confirmation

        Generates **BUY / HOLD / SELL** signals for broad market exposure.
        """
    )
    st.page_link("pages/1_Macro_Model.py", label="Go to Macro Model →", icon="📊")

with col2:
    st.subheader("🔄 Sector Rotation Model")
    st.markdown(
        """
        GICS sector rotation strategy using:
        - **CRSP / Compustat** sector return data via WRDS
        - **IBES analyst recommendation momentum** as a second factor
        - **70 / 30 combined score**: momentum + analyst revisions
        - **Optional macro overlay** for cyclical/defensive tilt
        - **Traffic light signals** — Green / Yellow / Red per sector

        Generates monthly long/short sector baskets.
        """
    )
    st.page_link("pages/2_Sector_Rotation.py", label="Go to Sector Rotation →", icon="🔄")

st.divider()

# ================================================================== STRATEGY DECISION PIPELINE
st.subheader("Strategy Decision Pipeline")
st.caption(
    "Which data feeds which signal — and how signals combine into portfolio actions. "
    "Band width reflects relative contribution."
)

_c = get_colors()
_is_dark = _c["plotly"] == "plotly_dark"
_bg = "#0d1117" if _is_dark else "#f7f9fc"
_font_col = "#d0dde8" if _is_dark else "#1a2535"

# ── Nodes ──────────────────────────────────────────────────────────────────
# 0  WRDS / CRSP         data source
# 1  Compustat           data source
# 2  FRED                data source
# 3  S&P 500 (yfinance)  data source
# 4  Sector Momentum     computation
# 5  Macro Score         computation
# 6  Sector Signals      signal  (Green / Yellow / Red)
# 7  Market Regime       signal  (BUY / HOLD / SELL)
# 8  Long Basket         output
# 9  Short Basket        output
# 10 Risk-Off / Cash     output

_sankey_labels = [
    "WRDS / CRSP",
    "Compustat",
    "FRED",
    "S&P 500",
    "Sector Momentum",
    "Macro Score",
    "Sector Signals",
    "Market Regime",
    "Long Basket",
    "Short Basket",
    "Risk-Off",
]

_sankey_colors_node = [
    "#4a7fb5",  # 0 WRDS/CRSP
    "#4a7fb5",  # 1 Compustat
    "#4a7fb5",  # 2 FRED
    "#4a7fb5",  # 3 S&P 500
    "#5a9abf",  # 4 Sector Momentum
    "#e07b39",  # 5 Macro Score
    "#b3863c",  # 6 Sector Signals
    "#e07b39",  # 7 Market Regime
    "#2ca02c",  # 8 Long Basket
    "#d62728",  # 9 Short Basket
    "#888888",  # 10 Risk-Off
]

# source → target : value (relative contribution weight)
_src = [0, 1,  2,  3,  4, 5, 5,  6, 6,  7,  7 ]
_tgt = [4, 4,  5,  5,  6, 6, 7,  8, 9,  8,  10]
_val = [4, 1,  2,  2,  4, 1, 2,  2, 1,  1,  2 ]

_link_colors = [
    "rgba(74,127,181,0.35)",   # WRDS → Momentum
    "rgba(74,127,181,0.20)",   # Compustat → Momentum
    "rgba(74,127,181,0.25)",   # FRED → Macro Score
    "rgba(74,127,181,0.25)",   # S&P → Macro Score
    "rgba(90,154,191,0.35)",   # Momentum → Sector Signals
    "rgba(224,123,57,0.25)",   # Macro Score → Sector Signals (macro adj)
    "rgba(224,123,57,0.35)",   # Macro Score → Market Regime
    "rgba(44,160,44,0.35)",    # Sector Signals → Long
    "rgba(214,39,40,0.30)",    # Sector Signals → Short
    "rgba(44,160,44,0.25)",    # Market Regime → Long (BUY)
    "rgba(136,136,136,0.35)",  # Market Regime → Risk-Off (SELL)
]

fig_sankey = go.Figure(go.Sankey(
    arrangement="snap",
    node=dict(
        pad=20,
        thickness=22,
        line=dict(color="rgba(0,0,0,0)", width=0),
        label=_sankey_labels,
        color=_sankey_colors_node,
        hovertemplate="<b>%{label}</b><extra></extra>",
    ),
    link=dict(
        source=_src,
        target=_tgt,
        value=_val,
        color=_link_colors,
        hovertemplate=(
            "%{source.label} → %{target.label}<br>"
            "Contribution weight: %{value}<extra></extra>"
        ),
    ),
))

fig_sankey.update_layout(
    paper_bgcolor=_bg,
    plot_bgcolor=_bg,
    height=420,
    margin=dict(l=10, r=10, t=10, b=10),
    font=dict(size=14, color=_font_col),
)

st.plotly_chart(fig_sankey, use_container_width=True)

st.divider()

today = pd.Timestamp.today().normalize()
last_completed_month_end = today.replace(day=1) - pd.Timedelta(days=1)
next_month_start = last_completed_month_end + pd.Timedelta(days=1)
next_month_end = last_completed_month_end + pd.offsets.MonthEnd(1)

macro_signal_as_of = last_completed_month_end
macro_backtest_end = last_completed_month_end
macro_signal_start = macro_signal_as_of - pd.DateOffset(months=6) + pd.offsets.MonthEnd(0)
macro_signal_end = macro_signal_as_of
macro_line_x = None
macro_line_y = None

macro_df = None
cached_macro = load_cached_macro_data(last_completed_month_end.strftime("%Y-%m-%d"))
if cached_macro is not None:
    sp_daily, sp_monthly, fred_dict = cached_macro
    macro_df = build_macro_signals(sp_daily, sp_monthly, fred_dict)
    macro_bt = run_macro_backtest(macro_df)
    valid_macro = macro_df.dropna(subset=["macro_score"])
    if not valid_macro.empty and not macro_bt.empty:
        macro_signal_as_of = pd.to_datetime(valid_macro.index.max())
        macro_backtest_end = pd.to_datetime(macro_bt.index.max())
        macro_signal_start = macro_signal_as_of - pd.DateOffset(months=6) + pd.offsets.MonthEnd(0)
        macro_signal_end = macro_signal_as_of
        next_month_start = macro_signal_as_of + pd.Timedelta(days=1)
        next_month_end = macro_signal_as_of + pd.offsets.MonthEnd(1)
        macro_line_x = macro_bt.index
        macro_line_y = macro_bt["strategy_cum"]

sector_signal_as_of = last_completed_month_end
sector_backtest_end = last_completed_month_end
sector_signal_end = sector_signal_as_of - pd.offsets.MonthEnd(DEFAULT_SKIP_MONTHS)
sector_signal_dates = pd.date_range(end=sector_signal_end, periods=DEFAULT_LOOKBACK_MONTHS, freq="ME")
sector_signal_start = sector_signal_dates.min()
sector_line_x = None
sector_line_y = None

sector_sig = None
cached_sector = load_cached_data()
if cached_sector is not None:
    sector_returns, fred, _ = cached_sector
    if not fred.empty and "macro_regime" not in fred.columns:
        fred["macro_regime"] = fred["yield_spread_10y_2y"].apply(label_macro_regime)
    _signals_module.fred = fred
    sector_sig = build_signals(
        sector_returns,
        lookback_months=DEFAULT_LOOKBACK_MONTHS,
        skip_months=DEFAULT_SKIP_MONTHS,
        top_n=DEFAULT_TOP_N,
        bottom_n=DEFAULT_BOTTOM_N,
        use_macro_overlay=USE_MACRO_OVERLAY,
    )
    sector_bt = run_backtest(sector_sig, top_n=DEFAULT_TOP_N)
    valid_sector = sector_sig.dropna(subset=["rank"])
    if not valid_sector.empty and not sector_bt.empty:
        sector_signal_as_of = pd.to_datetime(valid_sector["date"].max())
        sector_backtest_end = pd.to_datetime(sector_bt["date"].max())
        sector_signal_end = sector_signal_as_of - pd.offsets.MonthEnd(DEFAULT_SKIP_MONTHS)
        sector_signal_dates = pd.date_range(end=sector_signal_end, periods=DEFAULT_LOOKBACK_MONTHS, freq="ME")
        sector_signal_start = sector_signal_dates.min()
        sector_line_x = sector_bt["date"].values
        sector_line_y = sector_bt["strategy_cum"].values

st.subheader("Signal Timing Windows")
st.caption(
    "Both strategies are monthly. These charts show which dates belong to the historical "
    "backtest, which dates are used to build the latest signal, and which upcoming month the "
    "signal is applied to."
)

st.markdown("**Macro Model**")
st.plotly_chart(
    build_signal_chart(
        title="Macro — Signal Building Window",
        signal_as_of=macro_signal_as_of,
        signal_start=macro_signal_start,
        signal_end=macro_signal_end,
        applied_start=macro_signal_as_of + pd.Timedelta(days=1),
        applied_end=macro_signal_as_of + pd.offsets.MonthEnd(1),
        line_x=macro_line_x,
        line_y=macro_line_y,
    ),
    use_container_width=True,
)
st.caption(
    f"As of {macro_signal_as_of.strftime('%Y-%m-%d')}, the macro model reads the latest "
    f"completed month-end inputs and applies that regime call to "
    f"{(macro_signal_as_of + pd.Timedelta(days=1)).strftime('%B %Y')}."
)

st.markdown("**Sector Rotation**")
st.plotly_chart(
    build_signal_chart(
        title="Sector — Signal Building Window",
        signal_as_of=sector_signal_as_of,
        signal_start=sector_signal_start,
        signal_end=sector_signal_end,
        applied_start=sector_signal_as_of + pd.Timedelta(days=1),
        applied_end=sector_signal_as_of + pd.offsets.MonthEnd(1),
        line_x=sector_line_x,
        line_y=sector_line_y,
    ),
    use_container_width=True,
)
st.caption(
    f"As of {sector_signal_as_of.strftime('%Y-%m-%d')}, sector rotation uses a "
    f"{DEFAULT_LOOKBACK_MONTHS}-month lookback ending {sector_signal_end.strftime('%Y-%m-%d')} "
    f"with a {DEFAULT_SKIP_MONTHS}-month skip, then applies the ranking to "
    f"{(sector_signal_as_of + pd.Timedelta(days=1)).strftime('%B %Y')}."
)

aggregate_bt = build_aggregate_backtest(
    macro_df=macro_df,
    sector_sig=sector_sig,
    top_n=DEFAULT_TOP_N,
    holding_months=3,
    sell_mode="defensive",
)

if not aggregate_bt.empty:
    st.divider()
    st.subheader("Aggregate Strategy Backtest")
    st.caption(
        "3-month overlapping holdings. Each month opens a new vintage using the latest macro and sector signals, "
        "holds it for 3 months, and reports the equal-weight average return of all active vintages. "
        "Macro BUY/HOLD runs the top-N sector basket; macro SELL rotates that vintage into defensive sectors. "
        "Benchmark = the same overlapping top-N sector basket without the macro sell filter."
    )

    aggregate_perf = summarize_aggregate_performance(aggregate_bt)
    _metric_cols = st.columns(4)
    _metric_map = {
        "Annualized Return": True,
        "Annualized Volatility": True,
        "Sharpe Ratio": False,
        "Max Drawdown": True,
    }

    for _col, _metric in zip(_metric_cols, aggregate_perf["Metric"]):
        _row = aggregate_perf[aggregate_perf["Metric"] == _metric].iloc[0]
        _is_pct = _metric_map[_metric]
        _fmt = (lambda v: f"{v:.2%}") if _is_pct else (lambda v: f"{v:.2f}")
        with _col:
            st.metric(
                _metric,
                _fmt(_row["Aggregate Strategy"]) if pd.notna(_row["Aggregate Strategy"]) else "—",
                delta=(
                    f"Benchmark: {_fmt(_row['Aggregate Benchmark'])}"
                    if pd.notna(_row["Aggregate Benchmark"])
                    else "—"
                ),
            )

    _fig_aggregate = go.Figure()
    _fig_aggregate.add_trace(go.Scatter(
        x=aggregate_bt["date"],
        y=aggregate_bt["strategy_cum"],
        mode="lines",
        name="Aggregate Strategy",
        line=dict(color="#1f77b4", width=2.5),
    ))
    _fig_aggregate.add_trace(go.Scatter(
        x=aggregate_bt["date"],
        y=aggregate_bt["benchmark_cum"],
        mode="lines",
        name="Aggregate Benchmark",
        line=dict(color="#ff7f0e", width=1.8, dash="dot"),
    ))
    _fig_aggregate.update_layout(
        title="Growth of $1 — Aggregate Strategy vs Top-N Sector Benchmark",
        xaxis_title="Date",
        yaxis_title="Growth of $1",
        template=get_plotly_template(),
        height=340,
        margin=dict(l=0, r=0, t=44, b=40),
        legend=dict(orientation="h", yanchor="top", y=-0.15, xanchor="left", x=0),
    )
    st.plotly_chart(_fig_aggregate, use_container_width=True)
    st.caption(
        "Benchmark logic: the same 3-month overlapping top-N sector basket, but without the macro sell filter. "
        "When the strategy rotates to defensives on macro SELL, the benchmark stays in the top-N basket."
    )

    _window_col1, _window_col2 = st.columns([1, 1])
    with _window_col1:
        st.caption(
            f"Backtest overlap window: {aggregate_bt['date'].min().strftime('%Y-%m-%d')} "
            f"to {aggregate_bt['date'].max().strftime('%Y-%m-%d')}."
        )
    with _window_col2:
        st.caption(
            f"Average active vintages: {aggregate_bt['active_vintages'].mean():.1f} "
            f"(target steady-state = 3)."
        )

st.divider()
st.caption("Use the sidebar navigation to switch between modules.")
