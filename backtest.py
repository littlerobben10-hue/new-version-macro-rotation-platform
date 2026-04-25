# ============================================================
# BLUE EAGLE SECTOR ROTATION DASHBOARD
# backtest.py — Backtest engine
# ============================================================

import numpy as np
import pandas as pd

from utils import annualized_return, annualized_vol, sharpe_ratio, max_drawdown


# -----------------------------
# 12) Backtest engine
# -----------------------------
def run_backtest(signal_df, top_n=3):
    df = signal_df.copy()

    # Use only rows with a valid score and forward return
    valid = df.dropna(subset=["rank", "fwd_1m_ret"]).copy()

    # Strategy: equally weight top N sectors, hold next month
    valid["selected"] = valid["rank"] <= top_n

    port = valid[valid["selected"]].groupby("date", as_index=False).agg(
        strategy_ret=("fwd_1m_ret", "mean")
    )

    # Equal-weight benchmark: average next-month return across all sectors
    bench = valid.groupby("date", as_index=False).agg(
        benchmark_ret=("fwd_1m_ret", "mean")
    )

    # Red basket and green basket diagnostics
    green = valid[valid["signal"] == "Green"].groupby("date", as_index=False).agg(
        green_ret=("fwd_1m_ret", "mean")
    )
    red = valid[valid["signal"] == "Red"].groupby("date", as_index=False).agg(
        red_ret=("fwd_1m_ret", "mean")
    )

    out = port.merge(bench, on="date", how="outer").merge(green, on="date", how="left").merge(red, on="date", how="left")
    out = out.sort_values("date").reset_index(drop=True)

    out["strategy_cum"] = (1 + out["strategy_ret"].fillna(0)).cumprod()
    out["benchmark_cum"] = (1 + out["benchmark_ret"].fillna(0)).cumprod()
    out["green_cum"] = (1 + out["green_ret"].fillna(0)).cumprod()
    out["red_cum"] = (1 + out["red_ret"].fillna(0)).cumprod()
    out["spread_ret"] = out["green_ret"] - out["red_ret"]
    out["spread_cum"] = (1 + out["spread_ret"].fillna(0)).cumprod()

    return out

def hit_rate(strategy, benchmark):
    s = pd.Series(strategy).dropna()
    b = pd.Series(benchmark).reindex(s.index).dropna()
    mask = s.notna() & b.notna()
    if mask.sum() == 0:
        return np.nan
    return float((s[mask] > b[mask]).mean())


def summarize_performance(bt):
    summary = pd.DataFrame({
        "Metric": [
            "Annualized Return",
            "Annualized Volatility",
            "Sharpe Ratio",
            "Max Drawdown",
            "Hit Rate vs Benchmark",
        ],
        "Strategy": [
            annualized_return(bt["strategy_ret"]),
            annualized_vol(bt["strategy_ret"]),
            sharpe_ratio(bt["strategy_ret"]),
            max_drawdown(bt["strategy_ret"]),
            hit_rate(bt["strategy_ret"], bt["benchmark_ret"]),
        ],
        "Benchmark": [
            annualized_return(bt["benchmark_ret"]),
            annualized_vol(bt["benchmark_ret"]),
            sharpe_ratio(bt["benchmark_ret"]),
            max_drawdown(bt["benchmark_ret"]),
            np.nan,
        ],
        "Green-Red Spread": [
            annualized_return(bt["spread_ret"]),
            annualized_vol(bt["spread_ret"]),
            sharpe_ratio(bt["spread_ret"]),
            max_drawdown(bt["spread_ret"]),
            np.nan,
        ],
    })
    return summary
