# ============================================================
# BLUE EAGLE SECTOR ROTATION DASHBOARD
# config.py — Parameters and constants
# ============================================================

# -----------------------------
# 2) User parameters
# -----------------------------
import pandas as pd

START_DATE = "2010-01-01"
# Last completed month end (e.g. if today is Apr 15, use Mar 31)
_today = pd.Timestamp.today().normalize()
END_DATE = (_today.replace(day=1) - pd.Timedelta(days=1)).strftime("%Y-%m-%d")

DEFAULT_LOOKBACK_MONTHS = 6
DEFAULT_SKIP_MONTHS     = 1
DEFAULT_TOP_N           = 3
DEFAULT_BOTTOM_N        = 3

USE_MACRO_OVERLAY = False   # phase 1 = False
SAVE_CSV_OUTPUTS  = False   # set True if you want CSVs written in Colab

# -----------------------------
# 3) Helper functions — constants
# -----------------------------
GICS_MAP = {
    "10": "Energy",
    "15": "Materials",
    "20": "Industrials",
    "25": "Consumer Discretionary",
    "30": "Consumer Staples",
    "35": "Health Care",
    "40": "Financials",
    "45": "Information Technology",
    "50": "Communication Services",
    "55": "Utilities",
    "60": "Real Estate"
}

CYCLICALS  = {"Energy", "Materials", "Industrials", "Consumer Discretionary", "Financials", "Information Technology", "Communication Services", "Real Estate"}
DEFENSIVES = {"Consumer Staples", "Health Care", "Utilities"}
