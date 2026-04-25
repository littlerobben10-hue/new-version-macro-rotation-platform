# ============================================================
# BLUE EAGLE SECTOR ROTATION DASHBOARD
# utils.py — Helper functions
# ============================================================

import numpy as np
import pandas as pd


# -----------------------------
# 3) Helper functions
# -----------------------------

def coerce_numeric(df, cols):
    for c in cols:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df

def annualized_return(r):
    r = pd.Series(r).dropna()
    if len(r) == 0:
        return np.nan
    cum = (1 + r).prod()
    years = len(r) / 12.0
    if years <= 0 or cum <= 0:
        return np.nan
    return cum ** (1 / years) - 1

def annualized_vol(r):
    r = pd.Series(r).dropna()
    if len(r) < 2:
        return np.nan
    return r.std() * np.sqrt(12)

def sharpe_ratio(r, rf=0.0):
    ar = annualized_return(r)
    av = annualized_vol(r)
    if pd.isna(ar) or pd.isna(av) or av == 0:
        return np.nan
    return (ar - rf) / av

def max_drawdown(r):
    r = pd.Series(r).dropna()
    if len(r) == 0:
        return np.nan
    wealth = (1 + r).cumprod()
    peak = wealth.cummax()
    dd = wealth / peak - 1
    return dd.min()

def compute_compound_return(x):
    x = pd.Series(x).dropna()
    if len(x) == 0:
        return np.nan
    return np.prod(1 + x) - 1

def traffic_light_from_rank(rank, n_sectors, top_n=3, bottom_n=3):
    if pd.isna(rank):
        return np.nan
    if rank <= top_n:
        return "Green"
    elif rank > n_sectors - bottom_n:
        return "Red"
    else:
        return "Yellow"

def zscore_by_date(df, value_col):
    out = df.copy()
    out["zscore"] = out.groupby("date")[value_col].transform(
        lambda x: (x - x.mean()) / x.std(ddof=0) if x.std(ddof=0) not in [0, np.nan] else np.nan
    )
    return out
