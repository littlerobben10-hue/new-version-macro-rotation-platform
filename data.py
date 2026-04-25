# ============================================================
# BLUE EAGLE SECTOR ROTATION DASHBOARD
# data.py — Data loading (WRDS + FRED)
# ============================================================

import hashlib
import os
import pickle

import numpy as np
import pandas as pd
import wrds
import yfinance as yf
from pandas_datareader import data as web

from config import START_DATE, END_DATE, GICS_MAP
from utils import coerce_numeric

SECTOR_ETF_MAP = {
    "Energy": "XLE",
    "Materials": "XLB",
    "Industrials": "XLI",
    "Consumer Discretionary": "XLY",
    "Consumer Staples": "XLP",
    "Health Care": "XLV",
    "Financials": "XLF",
    "Information Technology": "XLK",
    "Communication Services": "XLC",
    "Utilities": "XLU",
    "Real Estate": "XLRE",
}


def _pull_yfinance_sector_returns(start_date, end_date):
    """Pull sector ETF monthly returns from yfinance to fill in months after CRSP."""
    tickers = list(SECTOR_ETF_MAP.values())
    px_data = yf.download(
        tickers=tickers,
        start=start_date,
        end=(pd.to_datetime(end_date) + pd.Timedelta(days=7)).strftime("%Y-%m-%d"),
        auto_adjust=True,
        progress=False,
        group_by="ticker",
        threads=True,
    )
    rows = []
    for sector, ticker in SECTOR_ETF_MAP.items():
        try:
            if ticker not in px_data:
                continue
            df_t = px_data[ticker].copy()
            if "Close" not in df_t.columns:
                continue
            s = df_t["Close"].dropna()
            if len(s) == 0:
                continue
            monthly = s.resample("ME").last().pct_change().dropna()
            rows.append(pd.DataFrame({
                "date": monthly.index,
                "sector": sector,
                "sector_ret": monthly.values,
                "n_stocks": np.nan,
                "sector_lag_cap": np.nan,
                "data_source": "yfinance_sector_etf",
            }))
        except Exception as e:
            print(f"yfinance pull failed for {ticker}: {e}")

    if not rows:
        return pd.DataFrame(columns=["date", "sector", "sector_ret", "n_stocks", "sector_lag_cap", "data_source"])

    out = pd.concat(rows, ignore_index=True)
    out["date"] = pd.to_datetime(out["date"]) + pd.offsets.MonthEnd(0)
    return out.sort_values(["sector", "date"]).reset_index(drop=True)

# Local disk cache directory (next to this file)
_CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".data_cache")


def _cache_path(wrds_username: str) -> str:
    """Return a per-user cache file path based on username + date range."""
    key = f"{wrds_username}_{START_DATE}_{END_DATE}"
    h = hashlib.md5(key.encode()).hexdigest()[:10]
    return os.path.join(_CACHE_DIR, f"sector_data_{h}.pkl")


def load_cached_data(wrds_username: str = None):
    """Load cached sector data from disk if available."""
    if not os.path.exists(_CACHE_DIR):
        return None

    if wrds_username:
        cache_file = _cache_path(wrds_username)
        if not os.path.exists(cache_file):
            return None
    else:
        cache_files = [
            os.path.join(_CACHE_DIR, fname)
            for fname in os.listdir(_CACHE_DIR)
            if fname.startswith("sector_data_") and fname.endswith(".pkl")
        ]
        if not cache_files:
            return None
        cache_file = max(cache_files, key=os.path.getmtime)

    with open(cache_file, "rb") as f:
        return pickle.load(f)


def load_data(wrds_username: str, wrds_password: str, status_cb=None, force_refresh: bool = False):
    """
    Loads and merges CRSP, CCM, Compustat, and FRED data.
    Credentials are passed in (no interactive prompts) for Streamlit compatibility.

    status_cb: optional callable(str) used to emit progress messages
               (e.g. a Streamlit st.status update function).

    Returns: sector_returns, fred, all_sectors
    """
    def _log(msg):
        if status_cb:
            status_cb(msg)
        else:
            print(msg)

    # ------------------------------------------------------------------
    # Fast path: load from local disk cache if available
    # ------------------------------------------------------------------
    os.makedirs(_CACHE_DIR, exist_ok=True)
    cache_file = _cache_path(wrds_username)

    if (not force_refresh) and os.path.exists(cache_file):
        _log("Loading from local cache (skipping WRDS query)…")
        with open(cache_file, "rb") as f:
            return pickle.load(f)

    # ------------------------------------------------------------------
    # 4) Connect to WRDS
    # ------------------------------------------------------------------
    _log("Connecting to WRDS…")
    db = wrds.Connection(wrds_username=wrds_username, password=wrds_password)

    # ------------------------------------------------------------------
    # 5) Pull CRSP monthly stock data
    # ------------------------------------------------------------------
    # Fetch only the columns needed for value-weighted sector returns.
    # ticker/comnam are dropped to reduce transfer size.
    _log("Querying CRSP monthly stock file (msf) — largest query, may take 1-3 min…")

    crsp_sql = f"""
    select
        a.permno,
        a.date,
        a.ret,
        a.prc,
        a.shrout,
        b.shrcd,
        b.exchcd
    from crsp.msf as a
    join crsp.msenames as b
        on a.permno = b.permno
       and b.namedt <= a.date
       and a.date <= b.nameendt
    where a.date between '{START_DATE}' and '{END_DATE}'
      and b.shrcd in (10, 11)
      and b.exchcd in (1, 2, 3)
    """

    crsp = db.raw_sql(crsp_sql, date_cols=["date"])
    crsp = coerce_numeric(crsp, ["ret", "prc", "shrout"])
    crsp = crsp.dropna(subset=["date", "permno", "ret", "prc", "shrout"]).copy()
    crsp["mkt_cap"] = crsp["prc"].abs() * crsp["shrout"]

    # ------------------------------------------------------------------
    # 6) Pull CRSP-Compustat link table
    # ------------------------------------------------------------------
    _log("Querying CCM link table…")
    ccm_sql = """
    select
        gvkey,
        lpermno as permno,
        linktype,
        linkprim,
        linkdt,
        linkenddt
    from crsp.ccmxpf_linktable
    where lpermno is not null
      and linktype in ('LU','LC','LS')
      and linkprim in ('P','C')
    """
    ccm = db.raw_sql(ccm_sql, date_cols=["linkdt", "linkenddt"])
    ccm["linkenddt"] = ccm["linkenddt"].fillna(pd.Timestamp("2100-12-31"))

    # ------------------------------------------------------------------
    # 7) Pull Compustat company GICS sector
    # ------------------------------------------------------------------
    _log("Querying Compustat GICS sectors…")
    comp_sql = """
    select
        gvkey,
        gsector
    from comp.company
    where gsector is not null
    """
    comp = db.raw_sql(comp_sql)
    comp["gsector"] = comp["gsector"].astype(str).str.strip()

    # ------------------------------------------------------------------
    # 11-13) Pull IBES analyst recommendations + CRSP-IBES link
    # ------------------------------------------------------------------
    _log("Querying IBES analyst recommendations…")
    rec_start = (pd.to_datetime(START_DATE) - pd.DateOffset(months=18)).strftime("%Y-%m-%d")

    rec = pd.DataFrame()
    try:
        rec_sql = f"""
        select
            ticker as ibes_ticker,
            statpers as stat_date,
            meanrec  as mean_rec,
            numrec   as num_rec
        from ibes.recdsum
        where statpers between '{rec_start}' and '{END_DATE}'
        """
        rec = db.raw_sql(rec_sql, date_cols=["stat_date"])
        rec["ibes_ticker"] = rec["ibes_ticker"].astype(str).str.strip()
        rec["mean_rec"]    = pd.to_numeric(rec["mean_rec"],  errors="coerce")
        rec["num_rec"]     = pd.to_numeric(rec["num_rec"],   errors="coerce")
        rec = rec.dropna(subset=["ibes_ticker", "stat_date", "mean_rec"])
        rec = rec[rec["num_rec"].fillna(0) >= 1]
        rec["date"] = pd.to_datetime(rec["stat_date"]) + pd.offsets.MonthEnd(0)
        rec = rec.sort_values(["ibes_ticker", "stat_date"]).drop_duplicates(["ibes_ticker", "date"], keep="last")
        _log(f"IBES recdsum rows: {len(rec):,}")
    except Exception as e:
        _log(f"IBES recdsum pull failed: {e}. Analyst factor will be skipped.")

    link_ibes = pd.DataFrame()
    if not rec.empty:
        try:
            link_sql = """
            select
                ticker    as ibes_ticker,
                permno,
                sdate     as link_start,
                edate     as link_end
            from wrdsapps.ibcrsphist
            where ticker  is not null
              and permno  is not null
            """
            link_ibes = db.raw_sql(link_sql, date_cols=["link_start", "link_end"])
            link_ibes["link_end"]    = link_ibes["link_end"].fillna(pd.Timestamp("2100-12-31"))
            link_ibes["ibes_ticker"] = link_ibes["ibes_ticker"].astype(str).str.strip()
            _log(f"IBES-CRSP link rows: {len(link_ibes):,}")
        except Exception as e:
            _log(f"IBES-CRSP link pull failed: {e}. Analyst factor will be skipped.")

    db.close()

    # ------------------------------------------------------------------
    # 8) Merge CRSP -> CCM -> Compustat sector
    # ------------------------------------------------------------------
    _log("Merging CRSP + CCM + Compustat…")
    merged = crsp.merge(ccm, how="left", on="permno")
    merged = merged[
        (merged["date"] >= merged["linkdt"]) &
        (merged["date"] <= merged["linkenddt"])
    ].copy()

    merged = merged.sort_values(["permno", "date", "gvkey"]).drop_duplicates(["permno", "date"], keep="first")

    merged = merged.merge(comp[["gvkey", "gsector"]], how="left", on="gvkey")
    merged["gsector"] = merged["gsector"].astype(str).str.strip()
    merged["sector"] = merged["gsector"].map(GICS_MAP)
    merged = merged[merged["sector"].notna()].copy()

    # ------------------------------------------------------------------
    # 9) Build lagged market cap and sector returns
    # ------------------------------------------------------------------
    _log("Computing value-weighted sector returns…")
    merged = merged.sort_values(["permno", "date"]).copy()
    merged["lag_mkt_cap"] = merged.groupby("permno")["mkt_cap"].shift(1)

    merged = merged.dropna(subset=["lag_mkt_cap", "ret"]).copy()
    merged = merged[merged["lag_mkt_cap"] > 0].copy()
    merged["date"] = pd.to_datetime(merged["date"]) + pd.offsets.MonthEnd(0)

    sector_totals = merged.groupby(["date", "sector"], as_index=False)["lag_mkt_cap"].sum()
    sector_totals = sector_totals.rename(columns={"lag_mkt_cap": "sector_lag_cap"})
    merged = merged.merge(sector_totals, on=["date", "sector"], how="left")
    merged["weight"] = merged["lag_mkt_cap"] / merged["sector_lag_cap"]

    sector_returns = merged.groupby(["date", "sector"], as_index=False).apply(
        lambda x: pd.Series({
            "sector_ret": np.sum(x["weight"] * x["ret"]),
            "n_stocks": x["permno"].nunique(),
            "sector_lag_cap": x["sector_lag_cap"].iloc[0]
        })
    ).reset_index(drop=True)

    # ------------------------------------------------------------------
    # 14-15) Map IBES recommendations → permno → sector, compute analyst momentum
    # ------------------------------------------------------------------
    analyst_sector = pd.DataFrame()
    if not rec.empty and not link_ibes.empty:
        try:
            rec_linked = rec.merge(link_ibes, how="left", on="ibes_ticker")
            rec_linked = rec_linked[
                (rec_linked["date"] >= rec_linked["link_start"]) &
                (rec_linked["date"] <= rec_linked["link_end"])
            ].copy()
            rec_linked = rec_linked.sort_values(["ibes_ticker", "date", "permno"]).drop_duplicates(
                ["ibes_ticker", "date"], keep="first"
            )
            rec_linked = rec_linked.dropna(subset=["permno"]).copy()
            rec_linked["permno"] = pd.to_numeric(rec_linked["permno"], errors="coerce")
            rec_linked = rec_linked.dropna(subset=["permno"]).copy()
            rec_linked["permno"] = rec_linked["permno"].astype(int)

            # 12-month change in mean recommendation (lower = more positive upgrades)
            rec_linked = rec_linked.sort_values(["permno", "date"]).copy()
            rec_linked["mean_rec_lag_12m"] = rec_linked.groupby("permno")["mean_rec"].shift(12)
            rec_linked["analyst_change_12m"] = rec_linked["mean_rec_lag_12m"] - rec_linked["mean_rec"]

            # Merge lag_mkt_cap from merged (stocks panel) for weighting
            stocks_cap = merged[["permno", "date", "lag_mkt_cap", "sector"]].copy()
            rec_stocks = rec_linked.merge(stocks_cap, how="left", on=["permno", "date"])
            rec_stocks = rec_stocks.dropna(subset=["analyst_change_12m", "lag_mkt_cap", "sector"]).copy()

            analyst_sector = (
                rec_stocks.groupby(["date", "sector"], as_index=False)
                .apply(lambda x: pd.Series({
                    "analyst_raw": (
                        np.sum(x["lag_mkt_cap"] * x["analyst_change_12m"]) / np.sum(x["lag_mkt_cap"])
                        if np.sum(x["lag_mkt_cap"]) > 0 else np.nan
                    ),
                    "analyst_names": x["permno"].nunique(),
                }))
                .reset_index(drop=True)
            )
            _log(f"Analyst sector rows: {len(analyst_sector):,}")
        except Exception as e:
            _log(f"Analyst sector aggregation failed: {e}. Analyst factor will be skipped.")

    all_dates = pd.date_range(sector_returns["date"].min(), sector_returns["date"].max(), freq="ME")
    all_sectors = list(GICS_MAP.values())
    grid = pd.MultiIndex.from_product([all_dates, all_sectors], names=["date", "sector"]).to_frame(index=False)

    sector_returns_crsp = grid.merge(sector_returns, how="left", on=["date", "sector"]).sort_values(["sector", "date"])

    # Attach analyst sector data to CRSP sector returns
    if not analyst_sector.empty:
        sector_returns_crsp = sector_returns_crsp.merge(analyst_sector, how="left", on=["date", "sector"])
    else:
        sector_returns_crsp["analyst_raw"]   = np.nan
        sector_returns_crsp["analyst_names"] = np.nan

    # ------------------------------------------------------------------
    # 10) Extend with yfinance for months after CRSP max date
    # ------------------------------------------------------------------
    _log("Extending sector returns with yfinance for recent months…")
    crsp_max_date = pd.to_datetime(sector_returns_crsp["date"].max()) if len(sector_returns_crsp) > 0 else pd.to_datetime(START_DATE)
    yf_start = (crsp_max_date - pd.offsets.MonthBegin(1)).strftime("%Y-%m-%d")

    sector_returns_yf = _pull_yfinance_sector_returns(yf_start, END_DATE)
    if len(sector_returns_yf) > 0:
        sector_returns_yf = sector_returns_yf[sector_returns_yf["date"] > crsp_max_date].copy()
        _log(f"yfinance added {len(sector_returns_yf):,} rows up to {sector_returns_yf['date'].max().date()}")

    # Ensure yfinance rows have analyst columns (NaN — no IBES data for recent months)
    for col in ["analyst_raw", "analyst_names"]:
        if col not in sector_returns_yf.columns:
            sector_returns_yf[col] = np.nan

    sector_returns = pd.concat([sector_returns_crsp, sector_returns_yf], ignore_index=True)
    sector_returns = sector_returns.drop_duplicates(["date", "sector"], keep="first").copy()

    all_dates = pd.date_range(sector_returns["date"].min(), sector_returns["date"].max(), freq="ME")
    grid2 = pd.MultiIndex.from_product([all_dates, all_sectors], names=["date", "sector"]).to_frame(index=False)
    sector_returns = grid2.merge(sector_returns, how="left", on=["date", "sector"]).sort_values(["sector", "date"])

    # Keep analyst coverage alive for recent months extended by yfinance.
    # If IBES has no fresh snapshot yet, use the most recent known sector-level analyst signal.
    for col in ["analyst_raw", "analyst_names"]:
        if col in sector_returns.columns:
            sector_returns[col] = sector_returns.groupby("sector")[col].ffill()

    # ------------------------------------------------------------------
    # 12) Pull FRED macro data
    # ------------------------------------------------------------------
    _log("Fetching FRED macro series…")
    fred_start = pd.to_datetime(START_DATE) - pd.DateOffset(months=24)

    fred_series = {}
    for series_code in ["DGS10", "DGS2", "UNRATE", "INDPRO"]:
        try:
            s = web.DataReader(series_code, "fred", fred_start, END_DATE)
            fred_series[series_code] = s
        except Exception as e:
            print(f"Could not pull FRED series {series_code}: {e}")

    if len(fred_series) > 0:
        fred = pd.concat(fred_series.values(), axis=1)
        fred.columns = list(fred_series.keys())
        fred = fred.resample("M").last().reset_index().rename(columns={"DATE": "date"})
        fred["date"] = pd.to_datetime(fred["DATE"] if "DATE" in fred.columns else fred["date"]) + pd.offsets.MonthEnd(0)
        fred["yield_spread_10y_2y"] = fred["DGS10"] - fred["DGS2"]
    else:
        fred = pd.DataFrame(columns=["date", "yield_spread_10y_2y", "UNRATE", "INDPRO"])

    result = (sector_returns, fred, all_sectors)

    # ------------------------------------------------------------------
    # Save to local disk cache for future sessions
    # ------------------------------------------------------------------
    _log("Saving to local cache for future loads…")
    with open(cache_file, "wb") as f:
        pickle.dump(result, f, protocol=pickle.HIGHEST_PROTOCOL)

    _log("Data ready.")
    return result


def clear_cache(wrds_username: str = None):
    """
    Delete cached data files. Pass wrds_username to clear only that user's cache,
    or omit to clear all cached files.
    """
    if not os.path.exists(_CACHE_DIR):
        return
    for fname in os.listdir(_CACHE_DIR):
        if fname.endswith(".pkl"):
            if wrds_username is None or _cache_path(wrds_username).endswith(fname):
                os.remove(os.path.join(_CACHE_DIR, fname))
