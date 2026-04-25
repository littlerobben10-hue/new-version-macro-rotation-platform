# ============================================================
# BLUE EAGLE MACRO MARKET MODEL
# macro_model.py — S&P 500 timing model using ISM / M2 / Rates + Momentum
# Parallel to the Sector Rotation strategy; uses yfinance + FRED only (no WRDS)
# ============================================================

import os
import pickle

import numpy as np
import pandas as pd
import yfinance as yf
from pandas_datareader import data as web

MACRO_START_DATE = "1980-01-01"
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data_cache")


def _macro_cache_path(end_date: str) -> str:
    safe_end = pd.to_datetime(end_date).strftime("%Y%m%d")
    return os.path.join(_CACHE_DIR, f"macro_data_{safe_end}.pkl")


def load_cached_macro_data(end_date: str = None):
    if end_date is None:
        end_date = pd.Timestamp.today().strftime("%Y-%m-%d")

    if not os.path.exists(_CACHE_DIR):
        return None

    cache_file = _macro_cache_path(end_date)
    if os.path.exists(cache_file):
        with open(cache_file, "rb") as f:
            return pickle.load(f)

    cache_files = [
        os.path.join(_CACHE_DIR, fname)
        for fname in os.listdir(_CACHE_DIR)
        if fname.startswith("macro_data_") and fname.endswith(".pkl")
    ]
    if not cache_files:
        return None

    latest_cache = max(cache_files, key=os.path.getmtime)
    with open(latest_cache, "rb") as f:
        return pickle.load(f)


# ------------------------------------------------------------------ data loader
def load_macro_data(end_date: str = None, force_refresh: bool = False) -> tuple:
    """
    Fetch S&P 500 (yfinance) and four FRED series needed by the macro model.
    Returns (sp_daily, sp_monthly, fred_dict) where fred_dict keys are series codes.
    No API key required — uses the public FRED endpoint via pandas_datareader.
    """
    if end_date is None:
        end_date = pd.Timestamp.today().strftime("%Y-%m-%d")

    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_file = _macro_cache_path(end_date)
    if (not force_refresh) and os.path.exists(cache_file):
        with open(cache_file, "rb") as f:
            return pickle.load(f)

    # ---- S&P 500 ----
    sp_raw = yf.download("^GSPC", start=MACRO_START_DATE, end=end_date,
                         auto_adjust=True, progress=False)
    sp_daily = sp_raw["Close"].squeeze()
    sp_daily.index = pd.to_datetime(sp_daily.index).tz_localize(None)
    sp_monthly = sp_daily.resample("ME").last()

    # ---- FRED ----
    # Pull from slightly before start so lagged calculations are valid
    fred_start = pd.to_datetime(MACRO_START_DATE) - pd.DateOffset(months=36)
    fred_codes = {
        "M2SL":    "M2 Money Supply",
        "CPIAUCSL": "CPI (All Urban Consumers)",
        "GS10":    "10-Year Treasury Yield",
        "NAPMNOI": "ISM Manufacturing New Orders",
    }
    fred_dict = {}
    for code in fred_codes:
        try:
            s = web.DataReader(code, "fred", fred_start, end_date)
            fred_dict[code] = s[code].resample("ME").last()
        except Exception as exc:
            print(f"[macro_model] Could not load FRED/{code}: {exc}")

    result = (sp_daily, sp_monthly, fred_dict)
    with open(cache_file, "wb") as f:
        pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)

    return result


# ------------------------------------------------------------------ signal builder
def build_macro_signals(sp_daily: pd.Series,
                        sp_monthly: pd.Series,
                        fred_dict: dict) -> pd.DataFrame:
    """
    Construct the three macro votes, momentum regime, combined signal.
    Returns a DataFrame indexed by month-end date.
    """
    df = pd.DataFrame(index=sp_monthly.index)
    df["sp"] = sp_monthly
    df["monthly_ret"] = sp_monthly.pct_change()
    df["fwd_6m_ret"] = sp_monthly.pct_change(6).shift(-6)

    # ---- ISM vote ----
    if "NAPMNOI" in fred_dict:
        ism = fred_dict["NAPMNOI"]
        df["ism"] = ism
        df["ism_3m_chg"] = df["ism"].diff(3)
        cond_cross = (df["ism"] > 50) & (df["ism"].shift(1) <= 50)
        cond_bounce = (df["ism"] < 50) & (df["ism_3m_chg"] >= 3)
        cond_trend  = (df["ism"] > 50) & (df["ism_3m_chg"] > 0)
        df["ism_vote"] = np.where(cond_cross | cond_bounce | cond_trend, 1, 0)
    else:
        df["ism"] = np.nan
        df["ism_3m_chg"] = np.nan
        df["ism_vote"] = 0

    # ---- Real M2 impulse vote ----
    if "M2SL" in fred_dict and "CPIAUCSL" in fred_dict:
        m2  = fred_dict["M2SL"]
        cpi = fred_dict["CPIAUCSL"]
        df["real_m2_yoy"] = m2.pct_change(12) * 100 - cpi.pct_change(12) * 100
        df["real_m2_impulse"] = df["real_m2_yoy"].diff(6)
        df["m2_vote"] = np.where(df["real_m2_impulse"] > 0, 1,
                        np.where(df["real_m2_impulse"] < 0, -1, 0))
    else:
        df["real_m2_impulse"] = np.nan
        df["m2_vote"] = 0

    # ---- 10Y rates vote ----
    if "GS10" in fred_dict:
        gs10 = fred_dict["GS10"]
        df["rate_signal"] = (-gs10.diff(24)).shift(18)
        df["rate_vote"] = np.where(df["rate_signal"] > 0, 1,
                          np.where(df["rate_signal"] < 0, -1, 0))
    else:
        df["rate_signal"] = np.nan
        df["rate_vote"] = 0

    # ---- Macro score & regime ----
    df["macro_score"] = df["ism_vote"] + df["m2_vote"] + df["rate_vote"]
    df["macro_regime"] = "Neutral"
    df.loc[df["macro_score"] >= 2,  "macro_regime"] = "Bullish"
    df.loc[df["macro_score"] <= -1, "macro_regime"] = "Bearish"

    # ---- Bloomberg-style momentum (14-day to 180-day) ----
    mom = pd.DataFrame(index=sp_monthly.index)
    mom["px_t_14"]  = sp_daily.shift(14).resample("ME").last()
    mom["px_t_180"] = sp_daily.shift(180).resample("ME").last()
    df["momentum"] = mom["px_t_14"] / mom["px_t_180"] - 1
    df["momentum_regime"] = np.where(df["momentum"] > 0, "Bullish",
                            np.where(df["momentum"] < 0, "Bearish", "Neutral"))

    # ---- Combined signal ----
    df["signal"] = "HOLD"
    df.loc[df["macro_regime"] == "Bullish", "signal"] = "BUY"
    df.loc[(df["macro_regime"] == "Bearish") &
           (df["momentum_regime"] == "Bearish"), "signal"] = "SELL"

    return df


# ------------------------------------------------------------------ backtest
def run_macro_backtest(df: pd.DataFrame) -> pd.DataFrame:
    """
    Long on BUY/HOLD, short on SELL; returns backtest DataFrame with cum returns.
    """
    bt = df.copy()
    bt["position"] = np.where(bt["signal"] == "SELL", -1.0, 1.0)
    bt["strategy_ret"] = bt["position"].shift(1) * bt["monthly_ret"]
    bt["buyhold_ret"]  = bt["monthly_ret"]
    bt = bt.dropna(subset=["strategy_ret", "buyhold_ret"]).copy()
    bt["strategy_cum"] = (1 + bt["strategy_ret"]).cumprod()
    bt["buyhold_cum"]  = (1 + bt["buyhold_ret"]).cumprod()
    return bt


# ------------------------------------------------------------------ perf summary
def summarize_macro_performance(bt: pd.DataFrame) -> dict:
    def _cagr(ret):
        ret = ret.dropna()
        return (1 + ret).prod() ** (12 / len(ret)) - 1

    def _vol(ret):
        return ret.dropna().std() * np.sqrt(12)

    def _sharpe(ret):
        v = _vol(ret)
        return _cagr(ret) / v if v != 0 else np.nan

    def _maxdd(ret):
        cum = (1 + ret.dropna()).cumprod()
        return (cum / cum.cummax() - 1).min()

    return {
        "cagr_strategy":  _cagr(bt["strategy_ret"]),
        "cagr_buyhold":   _cagr(bt["buyhold_ret"]),
        "sharpe_strategy": _sharpe(bt["strategy_ret"]),
        "sharpe_buyhold":  _sharpe(bt["buyhold_ret"]),
        "maxdd_strategy":  _maxdd(bt["strategy_ret"]),
        "maxdd_buyhold":   _maxdd(bt["buyhold_ret"]),
        "sell_freq":       (bt["strategy_ret"].index.isin(
                                bt.index[bt.shape[0] - 1:]
                            )).mean(),   # placeholder; computed in app
    }
