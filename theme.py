# ============================================================
# theme.py — Theme helpers using Streamlit's built-in theme
# ============================================================
import streamlit as st

# ── Colour palettes ──────────────────────────────────────────────────────────
_DARK = {
    "plotly":       "plotly_dark",
    "buy_bg":       "#1b4332",
    "hold_bg":      "#33291a",
    "sell_bg":      "#3b0d0c",
    "card_border":  "#444444",
    "text":         "#fafafa",
    "subtext":      "#aaaaaa",
    "green_row":    "background-color:#1b4332",
    "yellow_row":   "background-color:#33291a",
    "red_row":      "background-color:#3b0d0c",
}

_LIGHT = {
    "plotly":       "plotly_white",
    "buy_bg":       "#d4edda",
    "hold_bg":      "#fff3cd",
    "sell_bg":      "#f8d7da",
    "card_border":  "#cccccc",
    "text":         "#262730",
    "subtext":      "#555555",
    "green_row":    "background-color:#d4edda",
    "yellow_row":   "background-color:#fff3cd",
    "red_row":      "background-color:#f8d7da",
}


# ── Public API ───────────────────────────────────────────────────────────────

def get_theme() -> str:
    """Return 'dark' or 'light' based on Streamlit's built-in theme."""
    base = st.get_option("theme.base")
    # st.get_option returns the base from config.toml or the user's runtime selection
    return "dark" if (base is None or str(base).lower() == "dark") else "light"


def get_colors() -> dict:
    return _DARK if get_theme() == "dark" else _LIGHT


def get_plotly_template() -> str:
    return get_colors()["plotly"]
