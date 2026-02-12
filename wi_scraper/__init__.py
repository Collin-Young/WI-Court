"""Public API surface for the WI scraper package."""

from .constants import ClassCode, DEFAULT_CLASS_CODES
from .scraper import build_windows, fetch_case_summaries, flatten_aggregated
from .client import WICourtClient

__all__ = [
    "ClassCode",
    "DEFAULT_CLASS_CODES",
    "WICourtClient",
    "build_windows",
    "fetch_case_summaries",
    "flatten_aggregated",
]
