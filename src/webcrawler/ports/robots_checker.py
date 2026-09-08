"""Port: outbound interface for checking robots.txt permissions."""

from __future__ import annotations

from typing import Protocol


class RobotsChecker(Protocol):
    """Determines whether a URL is allowed to be fetched per robots.txt."""

    async def is_allowed(self, url: str, user_agent: str) -> bool: ...
