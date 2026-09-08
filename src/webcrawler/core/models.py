"""Domain models shared across the crawler core and its ports."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CrawlConfig:
    """Configuration for a crawl run."""

    max_concurrency: int = 10
    request_timeout: float = 10.0
    max_pages: int = 100
    delay: float = 0.0
    respect_robots: bool = True
    user_agent: str = "webcrawler/0.1"

    def __post_init__(self) -> None:
        if self.max_concurrency <= 0:
            raise ValueError("max_concurrency must be greater than zero")
        if self.request_timeout <= 0:
            raise ValueError("request_timeout must be greater than zero")
        if self.max_pages <= 0:
            raise ValueError("max_pages must be greater than zero")
        if self.delay < 0:
            raise ValueError("delay must not be negative")


@dataclass(frozen=True, slots=True)
class FetchResult:
    """The outcome of fetching a single URL."""

    url: str
    final_url: str | None = None
    status_code: int | None = None
    html: str | None = None
    content_type: str | None = None
    error: str | None = None

    @property
    def is_html(self) -> bool:
        return self.content_type is not None and "html" in self.content_type.lower()

    @property
    def ok(self) -> bool:
        return self.error is None and self.status_code is not None and self.status_code < 400


@dataclass(frozen=True, slots=True)
class PageReport:
    """A single crawled page and the links discovered on it, ready for output."""

    url: str
    links: tuple[str, ...] = ()
    error: str | None = None
