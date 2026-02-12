"""Constants for the Wisconsin Circuit Court Access scraper."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Tuple

BASE_URL = "https://wcca.wicourts.gov"

@dataclass(frozen=True)
class ClassCode:
    code: str
    label: str

DEFAULT_CLASS_CODES: Tuple[ClassCode, ...] = (
    ClassCode("50111", "Wills filed - no probate"),
    ClassCode("50101", "Probate Unscheduled"),
    ClassCode("30401", "Foreclosure of Mortgage"),
    ClassCode("30402", "Agricultural Foreclosure"),
    ClassCode("30902", "Small Claims, Eviction Due to Foreclosure"),
    ClassCode("30901", "Small Claims, Eviction"),
    ClassCode("30703", "Municipal Utility Lien"),
    ClassCode("30701", "Construction Lien"),
)
