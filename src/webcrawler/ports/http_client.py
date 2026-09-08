"""Port: outbound interface for fetching a URL over HTTP(S).

The core crawl engine depends on this abstraction, not on any concrete HTTP
library, so the HTTP adapter can be swapped freely (e.g. httpx -> requests
-> aiohttp) without touching crawl orchestration logic.
"""

from __future__ import annotations

from typing import Protocol

from webcrawler.core.models import FetchResult


class HttpClient(Protocol):
    """Fetches a single URL and returns a FetchResult, never raising on
    network/HTTP errors -- those are captured in FetchResult.error."""

    async def fetch(self, url: str) -> FetchResult: ...

    async def aclose(self) -> None: ...
