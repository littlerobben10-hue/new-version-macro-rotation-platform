# ============================================================
# BLUE EAGLE SECTOR ROTATION DASHBOARD
# signals.py — Signal engine
# ============================================================

import numpy as np
import pandas as pd

from config import CYCLICALS, DEFENSIVES
from utils import compute_compound_return, zscore_by_date, traffic_light_from_rank

MOMENTUM_WEIGHT = 0.70
ANALYST_WEIGHT  = 0.30

# fred is set by main.py after data loading:  signals.fred = fred
fred = pd.DataFrame()


def label_macro_regime(spread):
    if pd.isna(spread):
        return np.nan
    if spread < 0:
        return "Contraction"
    elif spread < 1:
        return "Neutral"
    else:
        return "Expansion"


# -----------------------------
# 11) Signal engine
# -----------------------------
def build_signals(sector_df, lookback_months=6, skip_months=1, top_n=3, bottom_n=3, use_macro_overlay=False):
    df = sector_df.copy().sort_values(["sector", "date"])

    # Momentum = compounded sector return over lookback window, skipping most recent months
    df["momentum_raw"] = (
        df.groupby("sector")["sector_ret"]
          .transform(lambda x: x.shift(skip_months).rolling(lookback_months).apply(compute_compound_return, raw=False))
    )

    df["n_sectors"] = df.groupby("date")["sector"].transform("count")

    # Cross-sectional z-scores
    df = zscore_by_date(df, "momentum_raw")
    df = df.rename(columns={"zscore": "momentum_z"})

    # Analyst z-score (if analyst_raw column was loaded from IBES)
    has_analyst = "analyst_raw" in df.columns and df["analyst_raw"].notna().any()
    if has_analyst:
        df = zscore_by_date(df, "analyst_raw")
        df = df.rename(columns={"zscore": "analyst_z"})
    else:
        df["analyst_raw"] = np.nan
        df["analyst_z"]   = np.nan

    # Combined score: 70% momentum + 30% analyst (fill NaN with 0 for sectors missing analyst data)
    df["momentum_z_filled"] = df["momentum_z"].fillna(0)
    df["analyst_z_filled"]  = df["analyst_z"].fillna(0)
    df["final_score"] = (
        MOMENTUM_WEIGHT * df["momentum_z_filled"] +
        ANALYST_WEIGHT  * df["analyst_z_filled"]
    )

    # Optional macro overlay (additive tilt on top of combined score)
    df["macro_adjustment"] = 0.0
    df["macro_regime"] = np.nan

    if use_macro_overlay and not fred.empty:
        df = df.merge(fred[["date", "yield_spread_10y_2y", "macro_regime"]], on="date", how="left")

        def macro_boost(row):
            reg = row["macro_regime"]
            sec = row["sector"]
            if pd.isna(reg):
                return 0.0
            if reg == "Expansion" and sec in CYCLICALS:
                return 0.25
            if reg == "Contraction" and sec in DEFENSIVES:
                return 0.25
            return 0.0

        df["macro_adjustment"] = df.apply(macro_boost, axis=1)
        df["final_score"] = df["final_score"] + df["macro_adjustment"]
    else:
        if "yield_spread_10y_2y" not in df.columns:
            df["yield_spread_10y_2y"] = np.nan

    # Rank by final_score; only rank rows where at least one signal exists
    has_signal = df["momentum_raw"].notna() | df["analyst_raw"].notna()
    df["rank"] = np.nan
    df.loc[has_signal, "rank"] = (
        df.loc[has_signal]
        .groupby("date")["final_score"]
        .rank(ascending=False, method="first")
    )

    # Traffic lights
    df["signal"] = df.apply(
        lambda r: traffic_light_from_rank(
            r["rank"],
            int(r["n_sectors"]) if not pd.isna(r["n_sectors"]) else 11,
            top_n,
            bottom_n,
        ),
        axis=1,
    )

    # Forward one-month return for backtest
    df["fwd_1m_ret"] = df.groupby("sector")["sector_ret"].shift(-1)

    return df
