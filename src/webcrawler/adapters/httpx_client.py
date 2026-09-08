"""HTTP client adapter backed by httpx.AsyncClient."""

from __future__ import annotations

import asyncio
from types import TracebackType

import httpx

from webcrawler.core.models import FetchResult
from webcrawler.ports.http_client import HttpClient as HttpClientPort

MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 0.1
RETRYABLE_STATUS_CODES = frozenset({408, 429, 500, 502, 503, 504})


class HttpxHttpClient(HttpClientPort):
    """Fetches URLs using httpx, translating all network/HTTP errors into
    FetchResult.error so the core engine never has to handle exceptions."""

    def __init__(self, timeout: float, user_agent: str) -> None:
        self._client = httpx.AsyncClient(
            timeout=timeout,
            headers={"User-Agent": user_agent},
            follow_redirects=True,
        )

    async def fetch(self, url: str) -> FetchResult:
        response: httpx.Response | None = None
        for attempt in range(MAX_ATTEMPTS):
            try:
                response = await self._client.get(url)
            except httpx.TimeoutException:
                if attempt < MAX_ATTEMPTS - 1:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
                    continue
                return FetchResult(url=url, error="Request timed out")
            except httpx.ConnectError as exc:
                if attempt < MAX_ATTEMPTS - 1:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
                    continue
                return FetchResult(url=url, error=f"Connection error: {exc}")
            except httpx.NetworkError as exc:
                if attempt < MAX_ATTEMPTS - 1:
                    await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
                    continue
                return FetchResult(url=url, error=f"Network error: {exc}")
            except httpx.HTTPError as exc:
                return FetchResult(url=url, error=f"HTTP error: {exc}")
            except Exception as exc:  # defensive: never let a fetch crash the crawl
                return FetchResult(url=url, error=f"Unexpected error: {exc}")

            if response.status_code in RETRYABLE_STATUS_CODES and attempt < MAX_ATTEMPTS - 1:
                await asyncio.sleep(RETRY_BACKOFF_SECONDS * (2**attempt))
                continue
            break

        if response is None:  # Defensive fallback; all retry branches return or set it.
            return FetchResult(url=url, error="Request failed without a response")
        content_type = response.headers.get("content-type")
        html: str | None = None
        if content_type and "html" in content_type.lower():
            html = response.text

        return FetchResult(
            url=url,
            final_url=str(response.url),
            status_code=response.status_code,
            html=html,
            content_type=content_type,
        )

    async def aclose(self) -> None:
        await self._client.aclose()

    async def __aenter__(self) -> HttpxHttpClient:
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        await self.aclose()
