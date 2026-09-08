"""Port: outbound interface for streaming crawl output as pages complete."""

from __future__ import annotations

from typing import Protocol

from webcrawler.core.models import PageReport


class OutputSink(Protocol):
    """Receives and emits a PageReport as soon as a page finishes crawling."""

    def emit(self, report: PageReport) -> None: ...
