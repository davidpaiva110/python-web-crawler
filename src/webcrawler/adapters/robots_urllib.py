"""robots.txt adapter using the stdlib urllib.robotparser.

robots.txt is fetched via httpx (async) and parsed synchronously with
RobotFileParser, which is fine since parsing is cheap CPU-only work.
Results are cached per-host to avoid refetching robots.txt for every page.
"""

from __future__ import annotations

import asyncio
from urllib.parse import urlparse
from urllib.robotparser import RobotFileParser

import httpx

from webcrawler.ports.robots_checker import RobotsChecker as RobotsCheckerPort


class RobotsTxtChecker(RobotsCheckerPort):
    """Fetches and caches robots.txt per host, then checks fetch permission."""

    def __init__(self, client: httpx.AsyncClient, timeout: float = 10.0) -> None:
        self._client = client
        self._timeout = timeout
        self._parsers: dict[str, RobotFileParser | None] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    async def is_allowed(self, url: str, user_agent: str) -> bool:
        parsed = urlparse(url)
        origin = f"{parsed.scheme}://{parsed.netloc}"
        parser = await self._get_parser(origin)
        if parser is None:
            # If robots.txt is unreachable/missing, default to allow.
            return True
        return parser.can_fetch(user_agent, url)

    async def _get_parser(self, origin: str) -> RobotFileParser | None:
        if origin in self._parsers:
            return self._parsers[origin]

        lock = self._locks.setdefault(origin, asyncio.Lock())
        async with lock:
            if origin in self._parsers:
                return self._parsers[origin]

            robots_url = f"{origin}/robots.txt"
            parser = RobotFileParser()
            parser.set_url(robots_url)
            try:
                response = await self._client.get(robots_url, timeout=self._timeout)
            except httpx.HTTPError:
                self._parsers[origin] = None
                return None

            if response.status_code >= 400:
                self._parsers[origin] = None
                return None

            parser.parse(response.text.splitlines())
            self._parsers[origin] = parser
            return parser

    async def aclose(self) -> None:
        await self._client.aclose()
