"""Data models for the Wisconsin Circuit Court Access scraper."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any, Dict, Optional, Set, Tuple

from .utils import parse_date


@dataclass(frozen=True)
class SearchWindow:
    """Represents an inclusive filing-date search window."""

    start: date
    end: date

    def as_payload(self) -> Dict[str, str]:
        return {
            "start": self.start.strftime("%m-%d-%Y"),
            "end": self.end.strftime("%m-%d-%Y"),
        }


@dataclass
class CaseSummary:
    """Normalized view of a case row returned by the API."""

    case_no: str
    caption: str
    county_name: str
    county_no: int
    party_name: str
    status: str
    filing_date: Optional[date]
    class_code: str
    dob: Optional[str]
    is_dob_sealed: bool
    raw: Dict[str, Any]

    @classmethod
    def from_api(cls, payload: Dict[str, Any], class_code: str) -> "CaseSummary":
        filing = parse_date(payload.get("filingDate"))
        return cls(
            case_no=payload["caseNo"],
            caption=payload.get("caption", ""),
            county_name=payload.get("countyName", ""),
            county_no=int(payload.get("countyNo", 0) or 0),
            party_name=payload.get("partyName", ""),
            status=payload.get("status", ""),
            filing_date=filing,
            class_code=class_code,
            dob=payload.get("dob"),
            is_dob_sealed=bool(payload.get("isDobSealed")),
            raw=payload,
        )


@dataclass
class AggregatedCase:
    """Represents a merged case potentially returned by multiple class-code searches."""

    summary: CaseSummary
    class_codes: Set[str] = field(default_factory=set)

    def key(self) -> Tuple[str, int]:
        return self.summary.case_no, self.summary.county_no

    def add_class_code(self, code: str) -> None:
        self.class_codes.add(code)


__all__ = ["SearchWindow", "CaseSummary", "AggregatedCase"]
