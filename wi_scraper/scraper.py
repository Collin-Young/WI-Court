"""High level orchestration for iterating WI advanced case searches."""

from __future__ import annotations

from collections import OrderedDict
from datetime import date
from typing import Dict, Iterator, List, Optional, Sequence, Tuple

from .client import WICourtClient
from .constants import ClassCode, DEFAULT_CLASS_CODES
from .models import AggregatedCase, SearchWindow
from .utils import iter_windows


def build_windows(
    *,
    start: date,
    end: Optional[date] = None,
    span_days: int = 7,
) -> Iterator[SearchWindow]:
    end_date = end or date.today()
    for window_start, window_end in iter_windows(start, end_date, span_days):
        yield SearchWindow(window_start, window_end)


def fetch_case_summaries(
    *,
    start: date,
    end: Optional[date] = None,
    class_codes: Sequence[ClassCode] = DEFAULT_CLASS_CODES,
    span_days: int = 7,
    client: Optional[WICourtClient] = None,
) -> Dict[Tuple[str, int], AggregatedCase]:
    """Iterate search windows and aggregate results keyed by (case_no, county_no)."""

    own_client = client is None
    session = client or WICourtClient()

    try:
        aggregated: "OrderedDict[Tuple[str, int], AggregatedCase]" = OrderedDict()
        for window in build_windows(start=start, end=end, span_days=span_days):
            for class_code in class_codes:
                summaries = session.advanced_case_search(window=window, class_code=class_code.code)
                for summary in summaries:
                    key = (summary.case_no, summary.county_no)
                    if key not in aggregated:
                        aggregated[key] = AggregatedCase(summary=summary)
                    aggregated[key].add_class_code(class_code.code)
        return aggregated
    finally:
        if own_client:
            session.close()


def flatten_aggregated(data: Dict[Tuple[str, int], AggregatedCase]) -> List[Dict[str, object]]:
    """Convert aggregated cases into serialisable dictionaries."""
    serialised: List[Dict[str, object]] = []
    for item in data.values():
        filing = item.summary.filing_date.isoformat() if item.summary.filing_date else None
        serialised.append(
            {
                "case_no": item.summary.case_no,
                "county_no": item.summary.county_no,
                "county_name": item.summary.county_name,
                "caption": item.summary.caption,
                "party_name": item.summary.party_name,
                "status": item.summary.status,
                "filing_date": filing,
                "dob": item.summary.dob,
                "is_dob_sealed": item.summary.is_dob_sealed,
                "class_codes": sorted(item.class_codes),
                "raw": item.summary.raw,
            }
        )
    return serialised


__all__ = ["build_windows", "fetch_case_summaries", "flatten_aggregated"]
