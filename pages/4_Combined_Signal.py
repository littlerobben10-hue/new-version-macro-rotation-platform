# ============================================================
# BLUE EAGLE — COMBINED PORTFOLIO SIGNAL PAGE
# pages/0_Combined_Signal.py
# ============================================================

import pandas as pd
import streamlit as st

import signals as _signals_module
from backtest import run_backtest
from config import (
    DEFAULT_BOTTOM_N,
    DEFAULT_LOOKBACK_MONTHS,
    DEFAULT_SKIP_MONTHS,
    DEFAULT_TOP_N,
    USE_MACRO_OVERLAY,
)
from data import load_cached_data
from macro_model import build_macro_signals, load_cached_macro_data, run_macro_backtest
from signals import build_signals, label_macro_regime
from theme import get_colors, get_plotly_template

st.set_page_config(
    page_title="Combined Signal — Blue Eagle",
    page_icon="🎯",
    layout="wide",
)

st.title("🎯 Combined Portfolio Signal")
st.caption(
    "Macro Model (Invest?) × Sector Model (Where?) → Portfolio Action. "
    "Both signals are monthly and based on the latest completed month-end data."
)
st.divider()

# ------------------------------------------------------------------ load data
today = pd.Timestamp.today().normalize()
last_month_end = today.replace(day=1) - pd.Timedelta(days=1)

macro_df = None
cached_macro = load_cached_macro_data(last_month_end.strftime("%Y-%m-%d"))
if cached_macro is not None:
    sp_daily, sp_monthly, fred_dict = cached_macro
    macro_df = build_macro_signals(sp_daily, sp_monthly, fred_dict)

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

# ------------------------------------------------------------------ extract latest values
macro_signal = None
macro_score  = None
macro_date   = None
sector_df    = None

if macro_df is not None:
    _valid = macro_df.dropna(subset=["macro_score"])
    if not _valid.empty:
        _row = _valid.iloc[-1]
        macro_signal = _row["signal"]
        macro_score  = int(_row["macro_score"])
        macro_date   = _row.name.strftime("%b %Y")

if sector_sig is not None:
    _latest_dt = sector_sig["date"].max()
    sector_df = sector_sig[sector_sig["date"] == _latest_dt].sort_values("rank").copy()

# ------------------------------------------------------------------ no data guard
if macro_signal is None and sector_df is None:
    st.info(
        "No cached model data found. Run the **Macro Model** or **Sector Rotation** pages first "
        "to generate signals, then return here."
    )
    st.page_link("pages/1_Macro_Model.py",   label="Go to Macro Model →",   icon="📊")
    st.page_link("pages/2_Sector_Rotation.py", label="Go to Sector Rotation →", icon="🔄")
    st.stop()

# ------------------------------------------------------------------ helpers
def portfolio_action(macro: str, sector_signal: str) -> str:
    if macro == "SELL":
        return "Risk Off"
    elif macro == "BUY":
        return {"Green": "Long", "Yellow": "Watch", "Red": "Avoid"}.get(sector_signal, "—")
    else:  # HOLD
        return {"Green": "Reduce", "Yellow": "Neutral", "Red": "Avoid"}.get(sector_signal, "—")


_c = get_colors()

# pre-compute sector counts
n_green, n_red, top_txt = 0, 0, "No data"
if sector_df is not None:
    greens   = sector_df[sector_df["signal"] == "Green"]["sector"].tolist()
    n_green  = len(greens)
    n_red    = int((sector_df["signal"] == "Red").sum())
    top_txt  = ", ".join(greens[:DEFAULT_TOP_N]) if greens else "None"

# derive portfolio action card content
ms = macro_signal or "HOLD"
if ms == "BUY" and n_green > 0:
    act_label  = "Invest + Tilt"
    act_detail = f"Long top {min(n_green, DEFAULT_TOP_N)} sectors"
    act_bg     = _c["buy_bg"]
elif ms == "SELL":
    act_label  = "Risk Off"
    act_detail = "Reduce / exit equity exposure"
    act_bg     = _c["sell_bg"]
elif ms == "HOLD":
    act_label  = "Cautious"
    act_detail = "Small size, rotate to quality"
    act_bg     = _c["hold_bg"]
else:
    act_label  = "—"
    act_detail = "Awaiting model data"
    act_bg     = _c["hold_bg"]

_sig_bg    = {"BUY": _c["buy_bg"], "HOLD": _c["hold_bg"], "SELL": _c["sell_bg"]}
_sig_emoji = {"BUY": "🟢", "HOLD": "🟡", "SELL": "🔴"}
macro_bg    = _sig_bg.get(ms, _c["hold_bg"])
macro_emoji = _sig_emoji.get(ms, "⬜")
score_txt   = f"Score: {macro_score:+d}" if macro_score is not None else "—"

# ================================================================== SIGNAL CARDS
col_m, col_s, col_a = st.columns(3)

with col_m:
    st.markdown(
        f"""<div style='background:{macro_bg};border:1px solid {_c["card_border"]};
        padding:24px;border-radius:12px;text-align:center;min-height:120px;'>
        <div style='font-size:0.82em;color:{_c["subtext"]}'>① Country Model</div>
        <div style='font-size:2.2em;font-weight:bold;margin-top:4px'>{macro_emoji} {ms}</div>
        <div style='font-size:0.82em;color:{_c["subtext"]};margin-top:6px'>
        {score_txt} &nbsp;·&nbsp; {macro_date or "—"}</div>
        </div>""",
        unsafe_allow_html=True,
    )

with col_s:
    st.markdown(
        f"""<div style='background:{_c["hold_bg"]};border:1px solid {_c["card_border"]};
        padding:24px;border-radius:12px;text-align:center;min-height:120px;'>
        <div style='font-size:0.82em;color:{_c["subtext"]}'>② Sector Model</div>
        <div style='font-size:1em;font-weight:bold;margin-top:6px'>{top_txt}</div>
        <div style='font-size:0.82em;color:{_c["subtext"]};margin-top:8px'>
        🟢 {n_green} Long &nbsp;|&nbsp; 🔴 {n_red} Avoid</div>
        </div>""",
        unsafe_allow_html=True,
    )

with col_a:
    st.markdown(
        f"""<div style='background:{act_bg};border:1px solid {_c["card_border"]};
        padding:24px;border-radius:12px;text-align:center;min-height:120px;'>
        <div style='font-size:0.82em;color:{_c["subtext"]}'>③ Portfolio Action</div>
        <div style='font-size:1.9em;font-weight:bold;margin-top:4px'>{act_label}</div>
        <div style='font-size:0.82em;color:{_c["subtext"]};margin-top:6px'>{act_detail}</div>
        </div>""",
        unsafe_allow_html=True,
    )

st.divider()

# ================================================================== ALLOCATION TABLE
st.subheader("Sector Allocation")

if sector_df is not None:
    tbl = sector_df[["sector", "signal", "rank", "momentum_raw", "final_score"]].copy()
    tbl["Momentum"]    = (tbl["momentum_raw"] * 100).round(2).astype(str) + "%"
    tbl["final_score"] = tbl["final_score"].round(3)
    tbl["rank"]        = tbl["rank"].astype("Int64")
    tbl["Portfolio Action"] = tbl["signal"].apply(lambda s: portfolio_action(ms, s))
    tbl = tbl.rename(columns={
        "sector": "Sector",
        "signal": "Sector Signal",
        "rank":   "Rank",
        "final_score": "Score",
    }).drop(columns=["momentum_raw"])

    _act_colors = {
        "Long":     _c["green_row"],
        "Reduce":   _c["green_row"],
        "Watch":    _c["yellow_row"],
        "Neutral":  _c["yellow_row"],
        "Avoid":    _c["red_row"],
        "Risk Off": _c["red_row"],
    }

    def _row_color(row):
        return [_act_colors.get(row["Portfolio Action"], "")] * len(row)

    st.dataframe(
        tbl[["Rank", "Sector", "Sector Signal", "Score", "Momentum", "Portfolio Action"]]
        .style.apply(_row_color, axis=1),
        use_container_width=True,
        hide_index=True,
    )
else:
    st.info("Load Sector Rotation data to see the allocation table.")

st.divider()

# ================================================================== COMBINATION LOGIC
with st.expander("Signal combination logic"):
    st.markdown(
        """
        The portfolio action is the intersection of the Country Model regime
        and the Sector Model traffic light:

        | Macro \\ Sector | 🟢 Green | 🟡 Yellow | 🔴 Red |
        |---|---|---|---|
        | 🟢 **BUY** | Long (full size) | Watch | Avoid |
        | 🟡 **HOLD** | Reduce (half size) | Neutral | Avoid |
        | 🔴 **SELL** | Risk Off | Risk Off | Risk Off |

        **Country Model trigger rules**
        - BUY: macro score ≥ 2
        - SELL: macro score ≤ −1 AND momentum is bearish
        - HOLD: everything else

        **Sector Model signal rules**
        - Green: ranked in the top N by final score
        - Red: ranked in the bottom N by final score
        - Yellow: middle ranks
        """
    )

st.caption("Signals are monthly. Navigate to the individual model pages for full detail and backtest performance.")
st.page_link("pages/1_Macro_Model.py",    label="Macro Model detail →",    icon="📊")
st.page_link("pages/2_Sector_Rotation.py", label="Sector Rotation detail →", icon="🔄")
