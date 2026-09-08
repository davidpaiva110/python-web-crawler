"""Port: outbound interface for extracting links from an HTML document."""

from __future__ import annotations

from typing import Protocol


class LinkExtractor(Protocol):
    """Extracts absolute link URLs from an HTML document body."""

    def extract_links(self, base_url: str, html: str) -> list[str]: ...
