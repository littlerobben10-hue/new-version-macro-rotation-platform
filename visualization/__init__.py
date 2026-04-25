"""
visualization package — Blue Eagle Platform
"""
from .strategy_explainer import (
    plot_strategy_explainer,
    build_sector_rotation_events,
    build_macro_model_events,
    DEFAULT_CONFIG,
)

__all__ = [
    "plot_strategy_explainer",
    "build_sector_rotation_events",
    "build_macro_model_events",
    "DEFAULT_CONFIG",
]
