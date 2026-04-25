# ============================================================
# BLUE EAGLE SECTOR ROTATION DASHBOARD
# main.py — Entry point: install, imports, initial run, widgets
# ============================================================

# -----------------------------
# 0) Install packages
# -----------------------------
import sys, subprocess, pkgutil

def pip_install(pkg):
    subprocess.check_call([sys.executable, "-m", "pip", "install", "-q", pkg])

required = ["wrds", "pandas_datareader", "plotly", "ipywidgets"]
for pkg in required:
    if pkgutil.find_loader(pkg) is None:
        pip_install(pkg)

# -----------------------------
# 1) Imports
# -----------------------------
import warnings
warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import ipywidgets as widgets
from IPython.display import display

from config import (
    START_DATE, END_DATE,
    DEFAULT_LOOKBACK_MONTHS, DEFAULT_SKIP_MONTHS,
    DEFAULT_TOP_N, DEFAULT_BOTTOM_N,
    USE_MACRO_OVERLAY
)
from data import load_data
import signals
import dashboard
from signals import build_signals
from backtest import run_backtest, summarize_performance
from dashboard import render_dashboard

# -----------------------------
# Load data
# -----------------------------
crsp, ccm, comp, merged, sector_returns, fred, all_sectors = load_data()

# Wire fred and all_sectors into modules that reference them as globals
signals.fred = fred
dashboard.fred = fred
dashboard.all_sectors = all_sectors
dashboard.sector_returns = sector_returns

# Wire fred macro_regime column
from signals import label_macro_regime
if not fred.empty:
    fred["macro_regime"] = fred["yield_spread_10y_2y"].apply(label_macro_regime)

# -----------------------------
# 13) Initial build
# -----------------------------
sig_init = build_signals(
    sector_returns,
    lookback_months=DEFAULT_LOOKBACK_MONTHS,
    skip_months=DEFAULT_SKIP_MONTHS,
    top_n=DEFAULT_TOP_N,
    bottom_n=DEFAULT_BOTTOM_N,
    use_macro_overlay=USE_MACRO_OVERLAY
)

backtest_init = run_backtest(sig_init, top_n=DEFAULT_TOP_N)
summary_init  = summarize_performance(backtest_init)

# -----------------------------
# 15) Widgets
# -----------------------------
available_dates = pd.Series(sorted(sector_returns["date"].dropna().unique()))
min_date = available_dates.min().date()
max_date = available_dates.max().date()

start_picker = widgets.DatePicker(description="Start", value=min_date)
end_picker = widgets.DatePicker(description="End", value=max_date)

lookback_slider = widgets.IntSlider(value=DEFAULT_LOOKBACK_MONTHS, min=3, max=12, step=1, description="Lookback")
skip_slider = widgets.IntSlider(value=DEFAULT_SKIP_MONTHS, min=0, max=2, step=1, description="Skip")
topn_slider = widgets.IntSlider(value=DEFAULT_TOP_N, min=1, max=5, step=1, description="Top N")
bottomn_slider = widgets.IntSlider(value=DEFAULT_BOTTOM_N, min=1, max=5, step=1, description="Bottom N")
macro_toggle = widgets.Checkbox(value=USE_MACRO_OVERLAY, description="Macro overlay")
run_button = widgets.Button(description="Run Dashboard", button_style="success")
output = widgets.Output()

def on_run_clicked(_):
    with output:
        render_dashboard(
            start_date=start_picker.value,
            end_date=end_picker.value,
            lookback_months=lookback_slider.value,
            skip_months=skip_slider.value,
            top_n=topn_slider.value,
            bottom_n=bottomn_slider.value,
            use_macro_overlay=macro_toggle.value
        )

run_button.on_click(on_run_clicked)

controls = widgets.VBox([
    widgets.HBox([start_picker, end_picker]),
    widgets.HBox([lookback_slider, skip_slider]),
    widgets.HBox([topn_slider, bottomn_slider]),
    widgets.HBox([macro_toggle, run_button]),
])

display(controls, output)

# Automatically render once on load
with output:
    render_dashboard(
        start_date=start_picker.value,
        end_date=end_picker.value,
        lookback_months=lookback_slider.value,
        skip_months=skip_slider.value,
        top_n=topn_slider.value,
        bottom_n=bottomn_slider.value,
        use_macro_overlay=macro_toggle.value
    )
