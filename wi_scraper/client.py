"""HTTP client for the Wisconsin Circuit Court Access JSON API."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Iterable, List, Optional

import httpx

from .constants import BASE_URL
from .models import CaseSummary, SearchWindow


class WICourtClient(AbstractContextManager["WICourtClient"]):
    """Thin wrapper around the ``jsonPost`` endpoints used by the UI."""

    def __init__(self, *, timeout: float = 30.0) -> None:
        self._client = httpx.Client(base_url=BASE_URL, timeout=timeout, headers={
            "Accept": "application/json, text/plain, */*",
            "Content-Type": "application/json;charset=UTF-8",
            "Origin": BASE_URL,
            "Referer": f"{BASE_URL}/advanced.html",
        })
        self._bootstrap()

    def _bootstrap(self) -> None:
        # Prime cookies/session so subsequent POSTs are accepted.
        response = self._client.get("/advanced.html")
        response.raise_for_status()

    def advanced_case_search(
        self,
        *,
        window: SearchWindow,
        class_code: str,
        include_missing_middle_name: bool = True,
        include_missing_dob: bool = True,
        attorney_type: str = "partyAtty",
    ) -> List[CaseSummary]:
        payload = {
            "includeMissingDob": include_missing_dob,
            "includeMissingMiddleName": include_missing_middle_name,
            "attyType": attorney_type,
            "classCode": class_code,
            "filingDate": window.as_payload(),
        }
        response = self._client.post("/jsonPost/advancedCaseSearch", json=payload)
        response.raise_for_status()
        data = response.json()
        result = data.get("result") or data.get("result", {}).get("result")  # defensive fallback
        if not result:
            return []
        raw_cases = result.get("cases", [])
        return [CaseSummary.from_api(item, class_code) for item in raw_cases]

    def close(self) -> None:  # pragma: no cover - trivial wrapper
        self._client.close()

    # Context manager support -------------------------------------------------
    def __enter__(self) -> "WICourtClient":  # pragma: no cover - convenience
        return self

    def __exit__(self, *exc_info) -> Optional[bool]:  # pragma: no cover - convenience
        self.close()
        return None


__all__ = ["WICourtClient"]
