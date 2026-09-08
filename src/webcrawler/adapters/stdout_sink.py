"""Output sink adapter that streams crawl results to stdout."""

from __future__ import annotations

from webcrawler.core.models import PageReport
from webcrawler.ports.output_sink import OutputSink as OutputSinkPort


class StdoutSink(OutputSinkPort):
    """Prints each page's URL, its error (if any), and its discovered links."""

    def emit(self, report: PageReport) -> None:
        print(report.url)
        if report.error:
            print(f"  ERROR: {report.error}")
        for link in report.links:
            print(f"  {link}")
        print()
