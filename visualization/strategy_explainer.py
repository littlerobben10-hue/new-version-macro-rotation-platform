"""
visualization/strategy_explainer.py
=====================================
Presentation-quality strategy decision-flow explainer — Blue Eagle Platform.

Design principles
-----------------
• At most 4 annotations, temporally distributed across the full time range.
• Annotations use paper (figure-fraction) y-coordinates so they sit in a
  fixed zone above the chart and never overlap the price line.
• Only meaningful BUY / SELL regime transitions are annotated.
• Regime background shading is limited to sustained runs (≥ 3 months).
• Each card shows exactly: STATE · DECISION · ACTION · OUTCOME.
• The connector arrow points from the card to the ACTUAL event on the
  price line (diagonal arrows are fine — they add spatial context).

Usage
-----
    from visualization.strategy_explainer import (
        plot_strategy_explainer,
        build_sector_rotation_events,
        build_macro_model_events,
    )

    events = build_macro_model_events(macro_df, macro_bt)
    fig = plot_strategy_explainer(
        df     = macro_bt["strategy_cum"],
        events = events,
        config = {"n_annotations": 4},
        title  = "Macro Model — Decision Flow",
    )
    st.plotly_chart(fig, use_container_width=True)
"""

from __future__ import annotations

import math
from typing import Any, Dict, List, Optional, Union

import numpy as np
import pandas as pd

# ─────────────────────────────────────────────────────────────────────────────
# Colours & layout defaults
# ─────────────────────────────────────────────────────────────────────────────
DEFAULT_CONFIG: Dict[str, Any] = {
    # chart
    "bg_color":          "#0d1117",
    "chart_color":       "#3a86c8",
    "chart_alpha":       0.80,
    "bench_color":       "#555555",
    "grid_color":        "#1a2030",
    # signal palette
    "buy_color":         "#2ca02c",
    "sell_color":        "#d62728",
    "hold_color":        "#f5c518",
    # annotation card borders (keyed by action_type)
    "card_border_buy":   "#2ca02c",
    "card_border_sell":  "#d62728",
    "card_border_hold":  "#f5c518",
    "card_border_other": "#4a7fb5",
    "card_bg":           "#111620",
    "card_text":         "#cccccc",
    "card_label_color":  "#888888",
    "connector_color":   "#444455",
    # annotation marker on the price line
    "marker_size":       10,
    # layout
    "n_annotations":     4,         # how many key events to annotate (3–5)
    "annot_paper_y_top": 0.99,      # top of annotation zone (paper fraction)
    "annot_paper_y_bot": 0.72,      # bottom of annotation zone (paper fraction)
    "chart_data_pct":    0.70,      # fraction of y-axis height reserved for chart data
    "min_regime_months": 3,         # minimum run length before shading a regime
    "figure_height":     620,
    "font_family":       "monospace",
    "font_size_label":   9,
    "font_size_body":    8,
}

# ─────────────────────────────────────────────────────────────────────────────
# Internal helpers
# ─────────────────────────────────────────────────────────────────────────────

def _cfg(user: Optional[Dict]) -> Dict[str, Any]:
    return {**DEFAULT_CONFIG, **(user or {})}


def _card_border(action_type: str, cfg: Dict) -> str:
    t = str(action_type).upper()
    if t in ("BUY",  "GREEN", "LONG"):  return cfg["card_border_buy"]
    if t in ("SELL", "RED",   "SHORT"): return cfg["card_border_sell"]
    if t in ("HOLD", "YELLOW"):         return cfg["card_border_hold"]
    return cfg["card_border_other"]


def _outcome_color(outcome: Optional[float], cfg: Dict) -> str:
    if outcome is None or (isinstance(outcome, float) and math.isnan(outcome)):
        return cfg["card_label_color"]
    return cfg["buy_color"] if outcome >= 0 else cfg["sell_color"]


def _fmt_outcome(outcome: Optional[float]) -> str:
    if outcome is None or (isinstance(outcome, float) and math.isnan(outcome)):
        return "—"
    sign = "+" if outcome > 0 else ""
    return f"{sign}{outcome:.1%}"


# ─────────────────────────────────────────────────────────────────────────────
# Smart event selector
# ─────────────────────────────────────────────────────────────────────────────

def _select_key_events(
    events: List[Dict[str, Any]],
    n: int,
) -> List[Dict[str, Any]]:
    """
    Select exactly n events that are:

    1. Temporally distributed — the time axis is divided into n equal segments;
       one event is chosen from each segment.
    2. Narratively significant — within each segment, prefer events where:
       • the absolute outcome is largest (biggest win or loss), AND
       • the signal is BUY or SELL (not HOLD), AND
       • the signal represents a *transition* (regime change).

    If a segment has no events, the nearest event from the full list is used.
    """
    if not events:
        return []
    if len(events) <= n:
        return sorted(events, key=lambda e: e["timestamp"])

    sorted_evs = sorted(events, key=lambda e: e["timestamp"])
    t_min = sorted_evs[0]["timestamp"]
    t_max = sorted_evs[-1]["timestamp"]
    total_days = max((t_max - t_min).days, 1)
    seg_days   = total_days / n

    # Narrative score: prefer large |outcome|, prefer BUY/SELL over HOLD
    def _score(ev: Dict) -> float:
        out = ev.get("outcome")
        out_mag = abs(out) if (out is not None and not math.isnan(out)) else 0.0
        sig_bonus = 1.5 if str(ev.get("signal", "")).upper() in ("BUY", "SELL",
                                                                   "GREEN", "RED") else 1.0
        return out_mag * sig_bonus

    selected: List[Dict[str, Any]] = []
    used: set = set()

    for i in range(n):
        seg_start = t_min + pd.Timedelta(days=i * seg_days)
        seg_end   = t_min + pd.Timedelta(days=(i + 1) * seg_days)

        candidates = [e for e in sorted_evs
                      if seg_start <= e["timestamp"] < seg_end
                      and id(e) not in used]

        if not candidates:
            # Fallback: nearest unused event to segment centre
            seg_mid  = t_min + pd.Timedelta(days=(i + 0.5) * seg_days)
            unused   = [e for e in sorted_evs if id(e) not in used]
            if not unused:
                continue
            candidates = [min(unused,
                              key=lambda e: abs((e["timestamp"] - seg_mid).days))]

        best = max(candidates, key=_score)
        selected.append(best)
        used.add(id(best))

    return selected


# ─────────────────────────────────────────────────────────────────────────────
# HTML card builder
# ─────────────────────────────────────────────────────────────────────────────

def _make_card_html(event: Dict, cfg: Dict) -> str:
    """
    Build the HTML text for one annotation card.

    Layout (vertical, single column):

        ▸ DATE
        ─────────────────
        STATE
          key: value  ×4
        ─────────────────
        DECISION → ACTION
          one-liner
        ─────────────────
        OUTCOME  +X.X%
    """
    ts          = event["timestamp"]
    action_type = str(event.get("action_type", "HOLD"))
    signal      = str(event.get("signal",      "HOLD")).upper()
    border_col  = _card_border(action_type, cfg)
    text_col    = cfg["card_text"]
    lbl_col     = cfg["card_label_color"]

    month_str   = ts.strftime("%b %Y")

    # ── STATE: top 4 items ────────────────────────────────────────────────────
    state_lines = [
        f"  {k}: {v}"
        for k, v in list(event["state"].items())[:4]
    ]
    state_html = "<br>".join(state_lines)

    # ── DECISION summary ─────────────────────────────────────────────────────
    dec_lines    = [l for l in event["decision"].split("\n") if l.strip()][:2]
    decision_str = "  " + " | ".join(dec_lines)

    # ── ACTION ───────────────────────────────────────────────────────────────
    action_lines = [l for l in event["action"].split("\n") if l.strip()]
    action_str   = action_lines[0] if action_lines else signal

    # ── OUTCOME ──────────────────────────────────────────────────────────────
    outcome      = event.get("outcome")
    out_str      = _fmt_outcome(outcome)
    out_col      = _outcome_color(outcome, cfg)

    SEP = f"<span style='color:{lbl_col}'>──────────────────</span>"

    html = (
        f"<b><span style='color:{border_col}'>{month_str}</span></b><br>"
        f"{SEP}<br>"
        f"<span style='color:{lbl_col}'>STATE</span><br>"
        f"<span style='color:{text_col}'>{state_html}</span><br>"
        f"{SEP}<br>"
        f"<span style='color:{lbl_col}'>DECISION → </span>"
        f"<b><span style='color:{border_col}'>{signal}</span></b><br>"
        f"<span style='color:{text_col}'>{decision_str}</span><br>"
        f"<span style='color:{text_col}'>  → {action_str}</span><br>"
        f"{SEP}<br>"
        f"<span style='color:{lbl_col}'>OUTCOME  </span>"
        f"<b><span style='color:{out_col}'>{out_str}</span></b>"
    )
    return html


# ─────────────────────────────────────────────────────────────────────────────
# Event builders  (unchanged logic — only the code that reads from the real
# signals.py / macro_model.py DataFrames)
# ─────────────────────────────────────────────────────────────────────────────

_SECTOR_ABBREV = {
    "Consumer Discretionary": "Cons. Disc.",
    "Consumer Staples":       "Cons. Staples",
    "Information Technology": "Info Tech",
    "Communication Services": "Comm. Svc",
    "Health Care":            "Health Care",
    "Industrials":            "Industrials",
    "Financials":             "Financials",
    "Energy":                 "Energy",
    "Materials":              "Materials",
    "Utilities":              "Utilities",
    "Real Estate":            "Real Estate",
}

def _abbrev(name: str) -> str:
    return _SECTOR_ABBREV.get(name, name)


def build_sector_rotation_events(
    sig_df: pd.DataFrame,
    bt_df: pd.DataFrame,
    top_n: int = 3,
    bottom_n: int = 3,
    signal_change_only: bool = True,
) -> List[Dict[str, Any]]:
    """
    Derive events from sector rotation signal + backtest DataFrames.
    One event per rebalance date where the top-N basket composition changes.
    """
    events: List[Dict[str, Any]] = []
    prev_top: Optional[frozenset] = None
    bt_index = bt_df.set_index("date") if "date" in bt_df.columns else bt_df

    for date in bt_index.index:
        date_rows = sig_df[sig_df["date"] == date].copy()
        if date_rows.empty:
            continue
        date_rows = date_rows.sort_values("rank")

        green  = date_rows[date_rows["signal"] == "Green"]["sector"].tolist()
        red    = date_rows[date_rows["signal"] == "Red"]["sector"].tolist()
        yellow = date_rows[date_rows["signal"] == "Yellow"]["sector"].tolist()

        top_set = frozenset(green)
        if signal_change_only and top_set == prev_top:
            continue
        prev_top = top_set

        top_row = date_rows.iloc[0] if not date_rows.empty else None

        has_macro  = ("macro_regime" in date_rows.columns
                      and not date_rows["macro_regime"].isna().all())
        macro_reg  = date_rows["macro_regime"].iloc[0] if has_macro else "N/A"
        has_spread = ("yield_spread_10y_2y" in date_rows.columns
                      and not date_rows["yield_spread_10y_2y"].isna().all())
        spread_val = date_rows["yield_spread_10y_2y"].iloc[0] if has_spread else None

        state: Dict[str, Any] = {}
        if top_row is not None:
            if pd.notna(top_row.get("momentum_raw")):
                state["Top momentum"] = f"{top_row['momentum_raw']:.2%}"
            if pd.notna(top_row.get("momentum_z")):
                state["Z-score (top)"] = f"{top_row['momentum_z']:.2f}"
            adj = top_row.get("macro_adjustment", 0.0)
            if pd.notna(adj) and adj != 0:
                state["Macro adj"] = f"+{adj:.2f}"
        state["Macro regime"] = str(macro_reg)
        if spread_val is not None and pd.notna(spread_val):
            state["10Y-2Y spread"] = f"{spread_val:.2f}%"
        state["# Sectors"] = str(len(date_rows))

        top_name  = top_row["sector"] if top_row is not None else "—"
        top_score = (top_row["final_score"]
                     if top_row is not None and pd.notna(top_row.get("final_score"))
                     else float("nan"))
        score_str = f"{top_score:.2f}" if not math.isnan(top_score) else "?"
        decision  = (
            f"Rank by final_score = z_score + macro_adj\n"
            f"#1: {top_name} (score {score_str})"
        )

        long_str   = ", ".join(_abbrev(s) for s in green) if green else "—"
        short_str  = ", ".join(_abbrev(s) for s in red)   if red   else "—"
        action     = f"LONG: {long_str}\nSHORT: {short_str}"
        action_type = "BUY" if green else ("SELL" if red else "HOLD")

        outcome: Optional[float] = None
        if date in bt_index.index:
            raw = bt_index.loc[date, "strategy_ret"]
            outcome = float(raw) if pd.notna(raw) else None

        events.append({
            "timestamp":   pd.Timestamp(date),
            "state":       state,
            "decision":    decision,
            "action":      action,
            "action_type": action_type,
            "outcome":     outcome,
            "signal":      action_type,
            "green":       green,
            "red":         red,
            "yellow":      yellow,
        })

    return events


def build_macro_model_events(
    macro_df: pd.DataFrame,
    macro_bt: pd.DataFrame,
    signal_change_only: bool = True,
) -> List[Dict[str, Any]]:
    """
    Derive events from macro model DataFrame + backtest.
    One event per BUY / HOLD / SELL transition.
    """
    events: List[Dict[str, Any]] = []
    prev_signal: Optional[str] = None
    bt_index = (macro_bt if macro_bt.index.dtype != object
                else macro_bt.set_index(macro_bt.columns[0]))

    def _vstr(v: float) -> str:
        return "+1" if v >= 1 else ("-1" if v <= -1 else " 0")

    for date, row in macro_df.iterrows():
        if pd.isna(row.get("macro_score")):
            continue
        signal = str(row.get("signal", "HOLD"))
        if signal_change_only and signal == prev_signal:
            continue
        prev_signal = signal

        state: Dict[str, Any] = {}
        if pd.notna(row.get("ism")):
            state["ISM"] = f"{row['ism']:.1f}  vote {_vstr(row.get('ism_vote',0))}"
        if pd.notna(row.get("real_m2_impulse")):
            state["Real M2"] = f"{row['real_m2_impulse']:+.2f}pp  vote {_vstr(row.get('m2_vote',0))}"
        if pd.notna(row.get("rate_signal")):
            state["Rate Δ"] = f"{row['rate_signal']:+.2f}pp  vote {_vstr(row.get('rate_vote',0))}"
        if pd.notna(row.get("momentum")):
            state["Momentum"] = (f"{row['momentum']:+.1%}  "
                                 f"{row.get('momentum_regime','—')}")

        score     = int(row.get("macro_score", 0))
        macro_reg = str(row.get("macro_regime",  "—"))
        mom_reg   = str(row.get("momentum_regime","—"))
        ism_v     = _vstr(row.get("ism_vote",  0))
        m2_v      = _vstr(row.get("m2_vote",   0))
        rate_v    = _vstr(row.get("rate_vote", 0))

        decision = (
            f"Score {ism_v}+{m2_v}+{rate_v} = {score:+d}\n"
            f"Macro: {macro_reg} | Mom: {mom_reg}"
        )

        if signal == "BUY":
            action = "Long S&P 500  (pos = +1)"
        elif signal == "SELL":
            action = "Flat / Short S&P 500  (pos = −1)"
        else:
            action = "Hold S&P 500  (pos = +1)"

        outcome: Optional[float] = None
        if date in bt_index.index:
            raw = bt_index.loc[date, "strategy_ret"]
            outcome = float(raw) if pd.notna(raw) else None

        events.append({
            "timestamp":   pd.Timestamp(date),
            "state":       state,
            "decision":    decision,
            "action":      action,
            "action_type": signal,
            "outcome":     outcome,
            "signal":      signal,
            "macro_score": score,
        })

    return events


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

def plot_strategy_explainer(
    df: Union[pd.Series, pd.DataFrame],
    events: List[Dict[str, Any]],
    config: Optional[Dict[str, Any]] = None,
    price_col: Optional[str] = None,
    title: str = "Strategy Decision Flow",
) -> Any:
    """
    Render a presentation-quality decision-flow chart.

    Parameters
    ----------
    df        : price / cumulative-return series (DatetimeIndex).
    events    : output of build_macro_model_events() or
                build_sector_rotation_events().
    config    : override any key in DEFAULT_CONFIG.
    price_col : column name if df is a DataFrame.
    title     : figure title.

    Returns a plotly Figure (add st.plotly_chart(fig) in Streamlit).
    """
    cfg = _cfg(config)

    series = (df[price_col] if isinstance(df, pd.DataFrame)
              and price_col and price_col in df.columns
              else df.iloc[:, 0] if isinstance(df, pd.DataFrame)
              else df).copy()
    series = series.dropna().sort_index()
    if not isinstance(series.index, pd.DatetimeIndex):
        series.index = pd.to_datetime(series.index)
    if series.empty:
        raise ValueError("price series is empty after dropna/sort_index()")

    return _build_plotly_figure(series, events, cfg, title)


# ─────────────────────────────────────────────────────────────────────────────
# Plotly rendering
# ─────────────────────────────────────────────────────────────────────────────

_ANNOT_ZONE_TOP = 0.990   # paper-y: very top of figure
_ANNOT_ZONE_BOT = 0.720   # paper-y: where annotation zone ends / chart begins
_CONNECTOR_BASE  = 0.715  # paper-y: where connector arrow tail starts


def _build_plotly_figure(
    series: pd.Series,
    events: List[Dict],
    cfg: Dict,
    title: str,
) -> Any:
    import plotly.graph_objects as go

    # ── y-axis: extend upward so the annotation zone paper-y 0.72–1.0
    #    never overlaps the price line.
    #    If chart data occupies paper-y 0.0 → 0.70, then:
    #       y_data_max  =  y_axis_min + 0.70 * (y_axis_max - y_axis_min)
    #    ⟹  y_axis_max  =  y_axis_min + (y_data_max - y_axis_min) / 0.70
    # ─────────────────────────────────────────────────────────────────────
    y_data_min  = float(series.min())
    y_data_max  = float(series.max())
    y_range     = max(y_data_max - y_data_min, 1e-6)
    data_frac   = cfg["chart_data_pct"]          # e.g. 0.70

    y_axis_min  = y_data_min - y_range * 0.04
    y_axis_max  = y_axis_min + (y_data_max - y_axis_min) / data_frac

    # ── base chart ──────────────────────────────────────────────────────
    fig = go.Figure()

    fig.add_trace(go.Scatter(
        x=series.index, y=series.values,
        mode="lines",
        name="Strategy",
        line=dict(color=cfg["chart_color"], width=2.5),
        opacity=cfg["chart_alpha"],
        hovertemplate="%{x|%b %Y}  %{y:.3f}<extra>Strategy</extra>",
    ))

    # ── sustained regime shading (BUY / SELL runs only) ─────────────────
    _add_regime_shading(fig, events, cfg)

    # ── buy / sell / hold markers on the price line ──────────────────────
    _add_signal_markers(fig, series, events, cfg)

    # ── annotation cards + connectors ────────────────────────────────────
    n = cfg["n_annotations"]
    key_events = _select_key_events(events, n)

    # evenly distribute card centres across paper-x [0.06, 0.94]
    card_paper_xs = _distribute_paper_x(key_events, series, lo=0.06, hi=0.94)

    n_cards = len(key_events)
    for i, (ev, card_px) in enumerate(zip(key_events, card_paper_xs)):
        if n_cards == 1:
            xanchor = "center"
        elif i == 0:
            xanchor = "left"
        elif i == n_cards - 1:
            xanchor = "right"
        else:
            xanchor = "center"
        _add_annotation_card(fig, ev, card_px, series, cfg, xanchor=xanchor)

    # ── layout ──────────────────────────────────────────────────────────
    x_min, x_max = series.index[0], series.index[-1]

    fig.update_layout(
        title=dict(text=title,
                   font=dict(color="#ffffff", size=14, family="Arial"),
                   x=0.02, y=0.98),
        paper_bgcolor=cfg["bg_color"],
        plot_bgcolor =cfg["bg_color"],
        height=cfg["figure_height"],
        margin=dict(l=60, r=30, t=30, b=50),
        xaxis=dict(
            range=[x_min, x_max],
            showgrid=True, gridcolor=cfg["grid_color"], gridwidth=1,
            tickfont=dict(color="#888888", size=10),
            title=dict(text="Date", font=dict(color="#888888")),
            zeroline=False,
        ),
        yaxis=dict(
            range=[y_axis_min, y_axis_max],
            showgrid=True, gridcolor=cfg["grid_color"], gridwidth=1,
            tickfont=dict(color="#888888", size=10),
            title=dict(text="Growth of $1", font=dict(color="#888888")),
            zeroline=False,
        ),
        legend=dict(
            orientation="h", x=0.0, y=-0.08,
            font=dict(color="#888888", size=10),
            bgcolor="rgba(0,0,0,0)",
        ),
        hovermode="x unified",
        hoverlabel=dict(bgcolor="#1a1d24", font_color="#ffffff",
                        bordercolor="#333333"),
    )

    return fig


def _distribute_paper_x(
    events: List[Dict],
    series: pd.Series,
    lo: float = 0.06,
    hi: float = 0.94,
) -> List[float]:
    """
    Evenly distribute card centres across [lo, hi] in paper coordinates.
    Cards are always spread across the full figure width regardless of when
    the underlying events occur — the connector arrow points to the actual
    data position on the price line.
    """
    if not events:
        return []
    n = len(events)
    if n == 1:
        return [(lo + hi) / 2]
    step = (hi - lo) / (n - 1)
    return [lo + i * step for i in range(n)]


def _add_regime_shading(fig, events: List[Dict], cfg: Dict) -> None:
    """
    Shade only sustained BUY or SELL regimes (≥ min_regime_months).
    No shading for HOLD / neutral periods — keeps the chart clean.
    """
    min_months = cfg["min_regime_months"]
    sig_colors = {"BUY": cfg["buy_color"], "SELL": cfg["sell_color"]}

    # Group into runs of the same signal
    runs: List[tuple] = []   # (signal, start_ts, end_ts)
    for ev in events:
        sig = str(ev.get("signal", "HOLD")).upper()
        if runs and runs[-1][0] == sig:
            runs[-1] = (sig, runs[-1][1], ev["timestamp"])
        else:
            runs.append((sig, ev["timestamp"], ev["timestamp"]))

    for sig, t_start, t_end in runs:
        if sig not in sig_colors:
            continue
        duration_months = (t_end - t_start).days / 30.0
        if duration_months < min_months:
            continue
        fig.add_vrect(
            x0=t_start, x1=t_end,
            fillcolor=sig_colors[sig],
            opacity=0.06,
            line_width=0,
            layer="below",
        )


def _add_signal_markers(
    fig, series: pd.Series, events: List[Dict], cfg: Dict
) -> None:
    """Coloured dots on the price line at each decision point."""
    import plotly.graph_objects as go

    groups: Dict[str, list] = {"BUY": [], "SELL": [], "HOLD": []}
    for ev in events:
        sig = str(ev.get("signal", "HOLD")).upper()
        bucket = sig if sig in groups else "HOLD"
        idx    = series.index.get_indexer([ev["timestamp"]], method="nearest")[0]
        groups[bucket].append((ev["timestamp"], float(series.iloc[idx]), ev))

    color_map = {
        "BUY":  cfg["buy_color"],
        "SELL": cfg["sell_color"],
        "HOLD": cfg["hold_color"],
    }
    symbol_map = {"BUY": "triangle-up", "SELL": "triangle-down", "HOLD": "circle"}

    for sig, pts in groups.items():
        if not pts:
            continue
        xs, ys, hovers = zip(*[
            (ts, price, _hover_text(ev))
            for ts, price, ev in pts
        ])
        fig.add_trace(go.Scatter(
            x=list(xs), y=list(ys),
            mode="markers",
            name=f"{sig} signal",
            marker=dict(
                color=color_map[sig],
                size=cfg["marker_size"],
                symbol=symbol_map[sig],
                line=dict(color="#ffffff", width=1),
            ),
            hovertext=list(hovers),
            hovertemplate="%{hovertext}<extra></extra>",
        ))


def _hover_text(ev: Dict) -> str:
    """Rich hover tooltip for a single event marker."""
    ts  = ev["timestamp"].strftime("%b %Y")
    sig = ev.get("signal", "—")
    out = _fmt_outcome(ev.get("outcome"))

    state_lines = [f"  {k}: {v}" for k, v in list(ev["state"].items())[:5]]
    dec_line    = ev["decision"].split("\n")[0] if ev.get("decision") else "—"

    lines = [
        f"<b>{ts}  ·  {sig}</b>",
        "<b>State</b>",
        *state_lines,
        f"<b>Decision</b>  {dec_line}",
        f"<b>Action</b>    {ev['action'].split(chr(10))[0]}",
        f"<b>Outcome</b>   {out}",
    ]
    return "<br>".join(lines)


def _add_annotation_card(
    fig,
    event: Dict,
    card_paper_x: float,
    series: pd.Series,
    cfg: Dict,
    xanchor: str = "center",
) -> None:
    """
    Draw one annotation card + connector for a key event.

    Card     — plotly annotation in paper coordinates (always same visual size,
               never overlaps the price line regardless of data scale).
    Connector — upward tick drawn directly from the event's data point using
               axref/ayref="pixel" (supported by all plotly 5.x versions).
               The card is horizontally centred near the event via paper-x
               derived from _distribute_paper_x(), so the tick and card are
               visually adjacent.
    """
    border_col = _card_border(event.get("action_type", "HOLD"), cfg)
    card_html  = _make_card_html(event, cfg)

    # ── card annotation — paper coordinates ──────────────────────────────
    fig.add_annotation(
        x=card_paper_x, xref="paper",
        y=_ANNOT_ZONE_TOP, yref="paper",
        xanchor=xanchor, yanchor="top",
        text=card_html,
        showarrow=False,
        align="left",
        bgcolor=cfg["card_bg"],
        bordercolor=border_col,
        borderwidth=1.8,
        borderpad=9,
        font=dict(
            family=cfg["font_family"],
            size=cfg["font_size_body"],
            color=cfg["card_text"],
        ),
        opacity=0.96,
    )

    # ── connector — pixel-offset upward tick from the event's data point ─
    #
    # axref/ayref="pixel": ax/ay are pixel offsets FROM the arrowhead (x,y).
    # ax=0 keeps the tail directly above the head.
    # ay=-N draws the tail N pixels above the head (upward in screen space).
    #
    # With figure_height ≈ 620px and ~55px top margin, the axes height is
    # ≈ 535px.  The chart data occupies the bottom 70 % → 375px.
    # A tick of -90px therefore spans ≈ 17 % of the axes height, just
    # reaching the annotation zone that begins at paper-y 0.72.
    ts    = event["timestamp"]
    idx   = series.index.get_indexer([ts], method="nearest")[0]
    price = float(series.iloc[idx])

    # ax=0, ay=N with no axref/ayref → plotly treats them as pixel offsets
    # (default pixel mode).  Negative ay = upward in screen space.
    tick_px = -max(70, int(cfg["figure_height"] * 0.13))   # scale with height

    fig.add_annotation(
        x=ts,    xref="x",
        y=price, yref="y",
        ax=0,
        ay=tick_px,
        showarrow=True,
        arrowhead=0,
        arrowwidth=1.4,
        arrowcolor=border_col,
        text="",
        opacity=0.60,
    )
