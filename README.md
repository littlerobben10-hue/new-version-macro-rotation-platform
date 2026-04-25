# Blue Eagle Macro & Sector Rotation Platform

Streamlit dashboard for macro timing, sector rotation signals, and combined portfolio backtests. The macro model uses public market and FRED data; the sector model requires WRDS access for CRSP, Compustat, and IBES data.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Optional WRDS credentials can be stored locally:

```bash
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
```

Then edit `.streamlit/secrets.toml` with your WRDS username and password.

## Run

```bash
streamlit run app.py
```

Open the local Streamlit URL shown in the terminal. Use the sidebar on the sector page to enter WRDS credentials, load data, or refresh the local cache.
