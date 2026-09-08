"""Core crawl orchestration: the async engine driving a single crawl run.

This module depends only on the ports (abstract interfaces) and pure
url_policy helpers -- never on concrete adapters -- keeping the dependency
direction pointed inward, per hexagonal architecture.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import suppress

from webcrawler.core.models import CrawlConfig, FetchResult, PageReport
from webcrawler.core.url_policy import (
    get_hostname,
    is_crawlable_scheme,
    is_same_host,
    normalize_url,
)
from webcrawler.ports.http_client import HttpClient
from webcrawler.ports.link_extractor import LinkExtractor
from webcrawler.ports.robots_checker import RobotsChecker


class CrawlEngine:
    """Coordinates fetching, link extraction, dedup, and traversal limits.

    Results are streamed via an async generator so callers (e.g. the CLI)
    can print each page as soon as it's done, rather than waiting for the
    whole crawl to finish.
    """

    def __init__(
        self,
        http_client: HttpClient,
        link_extractor: LinkExtractor,
        robots_checker: RobotsChecker | None,
        config: CrawlConfig,
    ) -> None:
        self._http = http_client
        self._extractor = link_extractor
        self._robots = robots_checker
        self._config = config

    async def crawl(self, base_url: str) -> AsyncIterator[PageReport]:
        base_url = normalize_url(base_url)
        base_hostname = get_hostname(base_url)
        if base_hostname is None:
            raise ValueError(f"Base URL has no hostname: {base_url}")

        visited: set[str] = {base_url}
        frontier: asyncio.Queue[str] = asyncio.Queue()
        frontier.put_nowait(base_url)

        results: asyncio.Queue[PageReport | None] = asyncio.Queue()
        dispatched = 0
        state_lock = asyncio.Lock()

        # Workers share the frontier: each processed page may add more URLs.
        # The lock makes the max-pages reservation atomic across workers.
        async def worker() -> None:
            nonlocal dispatched
            while True:
                url = await frontier.get()
                try:
                    async with state_lock:
                        if dispatched >= self._config.max_pages:
                            continue
                        dispatched += 1
                    report = await self._process_url(url, base_hostname, visited, frontier)
                    await results.put(report)
                    if self._config.delay:
                        await asyncio.sleep(self._config.delay)
                finally:
                    # Every queue item must be acknowledged, including URLs
                    # skipped after the max-pages limit has been reached.
                    frontier.task_done()

        num_workers = max(1, self._config.max_concurrency)
        workers = [asyncio.create_task(worker()) for _ in range(num_workers)]

        async def wait_and_close() -> None:
            # join() waits until workers finish the current frontier and mark
            # every discovered URL done; then no more work can be generated.
            await frontier.join()
            # Workers wait indefinitely for more URLs, so stop them once the
            # frontier is exhausted and signal the result consumer to finish.
            for task in workers:
                task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)
            await results.put(None)

        closer = asyncio.create_task(wait_and_close())

        try:
            # Reports are yielded as workers complete instead of being
            # buffered until the entire crawl has finished.
            while True:
                report = await results.get()
                if report is None:
                    break
                yield report
        finally:
            # If the caller closes the generator early, stop both the
            # completion task and workers so no request continues in the
            # background after the crawl has been cancelled.
            closer.cancel()
            with suppress(asyncio.CancelledError):
                await closer
            for worker_task in workers:
                worker_task.cancel()
            await asyncio.gather(*workers, return_exceptions=True)

    async def _process_url(
        self,
        url: str,
        base_hostname: str,
        visited: set[str],
        frontier: asyncio.Queue[str],
    ) -> PageReport:
        if self._robots is not None and self._config.respect_robots:
            allowed = await self._robots.is_allowed(url, self._config.user_agent)
            if not allowed:
                return PageReport(url=url, links=(), error="Disallowed by robots.txt")

        fetch_result: FetchResult = await self._http.fetch(url)

        if fetch_result.error is not None:
            return PageReport(url=url, links=(), error=fetch_result.error)

        effective_url = fetch_result.final_url or url
        effective_hostname = get_hostname(effective_url)
        if effective_hostname != base_hostname:
            return PageReport(
                url=url,
                links=(),
                error=f"Redirected outside allowed hostname: {effective_url}",
            )

        if fetch_result.status_code is not None and fetch_result.status_code >= 400:
            return PageReport(url=url, links=(), error=f"HTTP {fetch_result.status_code}")

        if not fetch_result.is_html or fetch_result.html is None:
            return PageReport(url=url, links=())

        try:
            raw_links = self._extractor.extract_links(effective_url, fetch_result.html)
        except Exception as exc:  # malformed HTML must not crash the crawl
            return PageReport(url=url, links=(), error=f"Failed to parse HTML: {exc}")

        links: list[str] = []
        for raw_link in raw_links:
            if not is_crawlable_scheme(raw_link):
                links.append(raw_link)
                continue
            normalized = normalize_url(raw_link)
            links.append(normalized)
            if is_same_host(normalized, base_hostname) and normalized not in visited:
                visited.add(normalized)
                await frontier.put(normalized)

        return PageReport(url=url, links=tuple(links))
