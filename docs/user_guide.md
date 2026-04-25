---
title: "Blue Eagle Macro & Sector Rotation Platform User Guide"
author: "Blue Eagle Capital"
date: "2026-04-24"
geometry: margin=1in
---

# 1. Overview

Blue Eagle Macro & Sector Rotation Platform is a Streamlit application for macro timing, sector rotation analysis, analyst recommendation signals, and combined strategy backtesting.

The platform is designed for:

- Reviewing the current macro market regime.
- Generating sector rotation rankings.
- Comparing cyclical and defensive sector behavior.
- Combining macro signals with sector momentum signals.
- Presenting an investment research framework, signal logic, and historical backtest results.

# 2. What Is Included

The project includes the following main components:

- `app.py`: Main Streamlit entry point and home page.
- `pages/1_Macro_Model.py`: Macro model page for macro indicators, signals, and backtests.
- `pages/2_Sector_Rotation.py`: Sector rotation page for rankings, momentum, analyst recommendations, and backtests.
- `pages/4_Combined_Signal.py`: Combined macro and sector signal page.
- `macro_model.py`: Macro data loading, macro signal construction, and macro backtest logic.
- `data.py`: Data loading logic for WRDS, CRSP, Compustat, IBES, and FRED.
- `signals.py`: Sector rotation signal calculation logic.
- `backtest.py`: Sector strategy backtest logic.
- `dashboard.py`, `theme.py`, and `visualization/`: Charting, layout, styling, and visualization helpers.
- `requirements.txt`: Python package dependencies.
- `.streamlit/secrets.toml.example`: WRDS credential template.
- `*.ipynb`: Jupyter notebooks used during research and development.

# 3. Data Sources

The platform uses the following data sources:

- WRDS / CRSP: Equity and sector return data.
- WRDS / Compustat: Company fundamentals and sector classification data.
- WRDS / IBES: Analyst recommendation data.
- FRED: Macroeconomic indicators.
- Yahoo Finance: Selected market index data.

The macro model mainly uses public data. The sector rotation model requires WRDS access.

# 4. Installation

From the project directory, create a virtual environment:

```bash
python -m venv .venv
source .venv/bin/activate
```

Install dependencies:

```bash
pip install -r requirements.txt
```

# 5. WRDS Configuration

WRDS is optional if you only use the macro model pages.

To use the sector rotation page, you need a WRDS username and password. You can create a local secrets file from the template:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Then edit `.streamlit/secrets.toml`:

```toml
[wrds]
username = "your_wrds_username"
password = "your_wrds_password"
```

You can also enter WRDS credentials directly in the Streamlit sidebar.

Important: `.streamlit/secrets.toml` is a local sensitive file and should not be uploaded to GitHub.

# 6. Run the Application

Run the following command from the project directory:

```bash
streamlit run app.py
```

The terminal will show a local URL, usually:

```text
http://localhost:8501
```

Open that URL in your browser to use the application.

# 7. Basic Workflow

1. Open the home page to review the overall framework and strategy logic.
2. Go to the Macro Model page to review macro indicators, macro signals, and macro backtest results.
3. Go to the Sector Rotation page, enter WRDS credentials, and load the data.
4. Wait for the data download and local cache update. The first load may take several minutes.
5. Review sector rankings, top sectors, bottom sectors, strategy performance, and related charts.
6. Go to the Combined Signal page to review the combined macro and sector allocation result.
7. If you need fresh data, clear the cache from the sidebar and reload the data.

# 8. Page Guide

## Home Page

The home page presents the Blue Eagle macro and sector rotation framework, including strategy logic, data sources, and the overall process diagram.

## Macro Model

The Macro Model page shows:

- Macro indicator trends.
- Macro scores and BUY / HOLD / SELL signals.
- Macro strategy backtest results.
- Macro regime implications for portfolio allocation.

## Sector Rotation

The Sector Rotation page shows:

- Sector momentum rankings.
- Analyst recommendation changes.
- Top N and bottom N sectors.
- Sector rotation strategy backtests.
- Local cache loading and WRDS data refresh controls.

## Combined Signal

The Combined Signal page shows:

- The combination of macro and sector signals.
- Sector allocation results under different macro regimes.
- Combined strategy performance and risk metrics.

# 9. Frequently Asked Questions

## Can I use the platform without a WRDS account?

Yes. You can use the macro model pages, but the sector rotation page cannot fully load CRSP, Compustat, and IBES data without WRDS access.

## Why is the first data load slow?

The first WRDS data pull may take several minutes. After a successful load, the platform writes a local cache so future loads are faster.

## How do I refresh the data?

Use the cache clear control on the Sector Rotation page sidebar, then reload the data.

## Why is `secrets.toml` not on GitHub?

The file may contain WRDS credentials, so it is excluded by `.gitignore`. GitHub only contains the safe template file, `.streamlit/secrets.toml.example`.

# 10. Summary

This platform combines macro timing, sector rotation, analyst recommendation signals, and portfolio backtesting in a single Streamlit dashboard. It helps users review market conditions, generate sector allocation views, and present historical strategy performance.
