# ============================================================
# BLUE EAGLE SECTOR ROTATION DASHBOARD
# dashboard.py — Dashboard rendering
# ============================================================

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from IPython.display import display, clear_output

from config import SAVE_CSV_OUTPUTS
from signals import build_signals
from backtest import run_backtest, summarize_performance

# all_sectors and fred are set by main.py after data loading:
#   dashboard.all_sectors = all_sectors
#   dashboard.fred = fred
all_sectors = []
fred = pd.DataFrame()


# -----------------------------
# 14) Dashboard function
# -----------------------------
def render_dashboard(start_date, end_date, lookback_months, skip_months, top_n, bottom_n, use_macro_overlay):
    clear_output(wait=True)

    sig = build_signals(
        sector_returns,
        lookback_months=int(lookback_months),
        skip_months=int(skip_months),
        top_n=int(top_n),
        bottom_n=int(bottom_n),
        use_macro_overlay=bool(use_macro_overlay)
    )

    bt = run_backtest(sig, top_n=int(top_n))

    # Filter display range
    start_date = pd.to_datetime(start_date) + pd.offsets.MonthEnd(0)
    end_date   = pd.to_datetime(end_date) + pd.offsets.MonthEnd(0)

    sig_f = sig[(sig["date"] >= start_date) & (sig["date"] <= end_date)].copy()
    bt_f  = bt[(bt["date"] >= start_date) & (bt["date"] <= end_date)].copy()

    if len(sig_f) == 0 or len(bt_f) == 0:
        print("No data in selected range.")
        return

    current_date = sig_f["date"].max()
    current = sig_f[sig_f["date"] == current_date].sort_values("rank").copy()

    perf = summarize_performance(bt_f)

    # Recompute cumulative in selected window
    bt_f["strategy_cum"]  = (1 + bt_f["strategy_ret"].fillna(0)).cumprod()
    bt_f["benchmark_cum"] = (1 + bt_f["benchmark_ret"].fillna(0)).cumprod()
    bt_f["spread_cum"]    = (1 + bt_f["spread_ret"].fillna(0)).cumprod()

    # ---- Print headers
    print("=" * 78)
    print("SECTOR ROTATION DASHBOARD")
    print("=" * 78)
    print(f"Date range: {start_date.date()} to {end_date.date()}")
    print(f"Lookback months: {lookback_months} | Skip months: {skip_months} | Top N: {top_n} | Bottom N: {bottom_n} | Macro overlay: {use_macro_overlay}")
    print(f"Latest signal date: {current_date.date()}")
    print("=" * 78)

    # ---- Current signal table
    show_cols = [
        "date", "sector", "momentum_raw", "momentum_z",
        "analyst_raw", "analyst_z",
        "macro_adjustment", "final_score", "rank", "signal", "n_stocks"
    ]
    show_cols = [c for c in show_cols if c in current.columns]
    current_show = current[show_cols].copy()
    for col, digits in [
        ("momentum_raw", 4),
        ("momentum_z", 3),
        ("analyst_raw", 4),
        ("analyst_z", 3),
        ("macro_adjustment", 3),
        ("final_score", 3),
    ]:
        if col in current_show.columns:
            current_show[col] = current_show[col].round(digits)

    print("\nCURRENT MONTH SIGNAL TABLE")
    display(current_show.reset_index(drop=True))

    # ---- Performance table
    print("\nBACKTEST SUMMARY")
    display(perf.style.format({
        "Strategy": "{:.2%}",
        "Benchmark": "{:.2%}",
        "Green-Red Spread": "{:.2%}"
    }, na_rep="NaN"))

    # Fix Sharpe rows to plain numbers
    perf2 = perf.copy()
    for c in ["Strategy", "Benchmark", "Green-Red Spread"]:
        perf2.loc[perf2["Metric"] == "Sharpe Ratio", c] = round(float(perf2.loc[perf2["Metric"] == "Sharpe Ratio", c].iloc[0]), 2) if pd.notna(perf2.loc[perf2["Metric"] == "Sharpe Ratio", c].iloc[0]) else np.nan
    display(perf2)

    # ---- Cumulative return chart
    fig1 = go.Figure()
    fig1.add_trace(go.Scatter(x=bt_f["date"], y=bt_f["strategy_cum"], mode="lines", name="Strategy"))
    fig1.add_trace(go.Scatter(x=bt_f["date"], y=bt_f["benchmark_cum"], mode="lines", name="Benchmark"))
    fig1.add_trace(go.Scatter(x=bt_f["date"], y=bt_f["spread_cum"], mode="lines", name="Green-Red Spread"))
    fig1.update_layout(
        title="Cumulative Performance",
        xaxis_title="Date",
        yaxis_title="Growth of $1",
        template="plotly_white",
        width=1000,
        height=500
    )
    fig1.show()

    # ---- Heatmap of traffic lights over time
    signal_to_num = {"Red": -1, "Yellow": 0, "Green": 1}
    hm = sig_f[["date", "sector", "signal"]].copy()
    hm["signal_num"] = hm["signal"].map(signal_to_num)
    heat = hm.pivot(index="sector", columns="date", values="signal_num").reindex(all_sectors)

    fig2 = px.imshow(
        heat,
        aspect="auto",
        title="Traffic Light Heatmap (Green=1, Yellow=0, Red=-1)",
        color_continuous_scale=["red", "yellow", "green"],
        zmin=-1,
        zmax=1
    )
    fig2.update_layout(width=1200, height=500)
    fig2.show()

    # ---- Current momentum bar chart
    fig3 = px.bar(
        current.sort_values("rank"),
        x="sector",
        y="momentum_raw",
        color="signal",
        title=f"Current Sector Momentum ({current_date.date()})",
        hover_data=["rank", "final_score", "n_stocks"]
    )
    fig3.update_layout(template="plotly_white", width=1000, height=500)
    fig3.show()

    # ---- Macro chart
    if not fred.empty:
        fred_f = fred[(fred["date"] >= start_date) & (fred["date"] <= end_date)].copy()
        fig4 = go.Figure()
        fig4.add_trace(go.Scatter(x=fred_f["date"], y=fred_f["yield_spread_10y_2y"], mode="lines", name="10Y-2Y Spread"))
        fig4.update_layout(
            title="FRED Macro Overlay Context: 10Y - 2Y Treasury Spread",
            xaxis_title="Date",
            yaxis_title="Spread",
            template="plotly_white",
            width=1000,
            height=400
        )
        fig4.show()

    # ---- Optional file saves
    if SAVE_CSV_OUTPUTS:
        sig_f.to_csv("sector_signals_filtered.csv", index=False)
        bt_f.to_csv("sector_backtest_filtered.csv", index=False)
        current_show.to_csv("current_signal_table.csv", index=False)
        print("\nCSV files saved to current Colab working directory.")
