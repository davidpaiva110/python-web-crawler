"""Integration-style tests for CrawlEngine against fake port implementations.

These fakes stand in for the HTTP client, link extractor, and robots
checker ports, letting us test crawl orchestration (dedup, same-domain
restriction, error handling, max-pages, robots behavior) without any real
or mocked network traffic.
"""

from __future__ import annotations

import asyncio

import pytest

from webcrawler.core.crawl_engine import CrawlEngine
from webcrawler.core.models import CrawlConfig, FetchResult, PageReport
from webcrawler.core.url_policy import resolve_link


class FakeHttpClient:
    def __init__(self, pages: dict[str, FetchResult]) -> None:
        self._pages = pages
        self.fetched_urls: list[str] = []

    async def fetch(self, url: str) -> FetchResult:
        self.fetched_urls.append(url)
        if url in self._pages:
            return self._pages[url]
        return FetchResult(url=url, error="not found in fake")

    async def aclose(self) -> None:
        pass


class FakeLinkExtractor:
    def __init__(self, links_by_url: dict[str, list[str]]) -> None:
        self._links_by_url = links_by_url

    def extract_links(self, base_url: str, html: str) -> list[str]:
        return self._links_by_url.get(base_url, [])


class RelativeLinkExtractor:
    def __init__(self) -> None:
        self.base_urls: list[str] = []

    def extract_links(self, base_url: str, html: str) -> list[str]:
        self.base_urls.append(base_url)
        return [resolve_link(base_url, "next")]


class AllowAllRobots:
    async def is_allowed(self, url: str, user_agent: str) -> bool:
        return True


class DenyAllRobots:
    async def is_allowed(self, url: str, user_agent: str) -> bool:
        return False


def html_page(url: str) -> FetchResult:
    return FetchResult(url=url, status_code=200, html="<html></html>", content_type="text/html")


async def collect(engine: CrawlEngine, base_url: str) -> list[PageReport]:
    return [report async for report in engine.crawl(base_url)]


@pytest.mark.asyncio
async def test_crawls_same_domain_and_stops_at_external_links() -> None:
    base = "http://example.com/"
    page_a = "http://example.com/a"
    external = "https://other.com/"

    pages = {
        base: html_page(base),
        page_a: html_page(page_a),
    }
    links = {
        base: [page_a, external],
        page_a: [],
    }

    http = FakeHttpClient(pages)
    engine = CrawlEngine(
        http_client=http,
        link_extractor=FakeLinkExtractor(links),
        robots_checker=AllowAllRobots(),
        config=CrawlConfig(max_concurrency=2, max_pages=10),
    )

    reports = await collect(engine, base)
    urls_crawled = {r.url for r in reports}

    assert base in urls_crawled
    assert page_a in urls_crawled
    assert external not in urls_crawled
    assert external not in http.fetched_urls


@pytest.mark.asyncio
async def test_deduplicates_pages_linked_multiple_times() -> None:
    base = "http://example.com/"
    page_a = "http://example.com/a"
    page_b = "http://example.com/b"

    pages = {base: html_page(base), page_a: html_page(page_a), page_b: html_page(page_b)}
    links = {
        base: [page_a, page_b],
        page_a: [page_b],  # page_b linked from two places
        page_b: [],
    }

    http = FakeHttpClient(pages)
    engine = CrawlEngine(
        http_client=http,
        link_extractor=FakeLinkExtractor(links),
        robots_checker=AllowAllRobots(),
        config=CrawlConfig(max_concurrency=2, max_pages=10),
    )

    await collect(engine, base)

    assert http.fetched_urls.count(page_b) == 1


@pytest.mark.asyncio
async def test_normalizes_equivalent_urls_before_dedup() -> None:
    base = "http://example.com/"
    variant = "http://EXAMPLE.com/a/"
    canonical = "http://example.com/a"

    pages = {base: html_page(base), canonical: html_page(canonical)}
    links = {base: [variant, canonical], canonical: []}

    http = FakeHttpClient(pages)
    engine = CrawlEngine(
        http_client=http,
        link_extractor=FakeLinkExtractor(links),
        robots_checker=AllowAllRobots(),
        config=CrawlConfig(max_concurrency=2, max_pages=10),
    )

    await collect(engine, base)

    assert http.fetched_urls.count(canonical) == 1


@pytest.mark.asyncio
async def test_reports_error_without_raising() -> None:
    base = "http://example.com/"
    broken = "http://example.com/broken"

    pages = {base: html_page(base), broken: FetchResult(url=broken, error="Connection error")}
    links = {base: [broken], broken: []}

    http = FakeHttpClient(pages)
    engine = CrawlEngine(
        http_client=http,
        link_extractor=FakeLinkExtractor(links),
        robots_checker=AllowAllRobots(),
        config=CrawlConfig(max_concurrency=2, max_pages=10),
    )

    reports = await collect(engine, base)
    broken_report = next(r for r in reports if r.url == broken)
    assert broken_report.error == "Connection error"


@pytest.mark.asyncio
async def test_reports_http_error_status() -> None:
    base = "http://example.com/"
    missing = "http://example.com/missing"

    pages = {
        base: html_page(base),
        missing: FetchResult(url=missing, status_code=404, content_type="text/html"),
    }
    links = {base: [missing], missing: []}

    http = FakeHttpClient(pages)
    engine = CrawlEngine(
        http_client=http,
        link_extractor=FakeLinkExtractor(links),
        robots_checker=AllowAllRobots(),
        config=CrawlConfig(max_concurrency=2, max_pages=10),
    )

    reports = await collect(engine, base)
    missing_report = next(r for r in reports if r.url == missing)
    assert missing_report.error == "HTTP 404"


@pytest.mark.asyncio
async def test_skips_non_html_content() -> None:
    base = "http://example.com/"
    image = "http://example.com/image.png"

    pages = {
        base: html_page(base),
        image: FetchResult(url=image, status_code=200, content_type="image/png"),
    }
    links = {base: [image]}

    http = FakeHttpClient(pages)
    engine = CrawlEngine(
        http_client=http,
        link_extractor=FakeLinkExtractor(links),
        robots_checker=AllowAllRobots(),
        config=CrawlConfig(max_concurrency=2, max_pages=10),
    )

    reports = await collect(engine, base)
    image_report = next(r for r in reports if r.url == image)
    assert image_report.links == ()
    assert image_report.error is None


@pytest.mark.asyncio
async def test_respects_robots_txt_disallow() -> None:
    base = "http://example.com/"

    pages = {base: html_page(base)}
    links = {base: []}

    http = FakeHttpClient(pages)
    engine = CrawlEngine(
        http_client=http,
        link_extractor=FakeLinkExtractor(links),
        robots_checker=DenyAllRobots(),
        config=CrawlConfig(max_concurrency=2, max_pages=10, respect_robots=True),
    )

    reports = await collect(engine, base)
    assert reports[0].error == "Disallowed by robots.txt"


@pytest.mark.asyncio
async def test_no_robots_flag_ignores_disallow() -> None:
    base = "http://example.com/"

    pages = {base: html_page(base)}
    links = {base: []}

    http = FakeHttpClient(pages)
    engine = CrawlEngine(
        http_client=http,
        link_extractor=FakeLinkExtractor(links),
        robots_checker=DenyAllRobots(),
        config=CrawlConfig(max_concurrency=2, max_pages=10, respect_robots=False),
    )

    reports = await collect(engine, base)
    assert reports[0].error is None


@pytest.mark.asyncio
async def test_respects_max_pages_limit() -> None:
    base = "http://example.com/"
    pages = {base: html_page(base)}
    links = {base: []}
    for i in range(20):
        url = f"http://example.com/page{i}"
        pages[url] = html_page(url)
        links[base].append(url)
        links[url] = []

    http = FakeHttpClient(pages)
    engine = CrawlEngine(
        http_client=http,
        link_extractor=FakeLinkExtractor(links),
        robots_checker=AllowAllRobots(),
        config=CrawlConfig(max_concurrency=5, max_pages=5),
    )

    reports = await collect(engine, base)
    assert len(reports) == 5


@pytest.mark.asyncio
async def test_does_not_parse_or_follow_cross_host_redirect() -> None:
    base = "http://example.com/"
    redirected = "https://other.example/landing"
    http = FakeHttpClient(
        {
            base: FetchResult(
                url=base,
                final_url=redirected,
                status_code=200,
                html="<a href='/secret'>secret</a>",
                content_type="text/html",
            )
        }
    )
    engine = CrawlEngine(
        http_client=http,
        link_extractor=FakeLinkExtractor({}),
        robots_checker=None,
        config=CrawlConfig(max_pages=1),
    )

    reports = await collect(engine, base)

    assert reports[0].error == f"Redirected outside allowed hostname: {redirected}"
    assert reports[0].links == ()
    assert http.fetched_urls == [base]


@pytest.mark.asyncio
async def test_resolves_links_against_same_host_redirect_destination() -> None:
    base = "http://example.com/"
    landing = "http://example.com/landing/"
    next_page = "http://example.com/landing/next"
    http = FakeHttpClient(
        {
            base: FetchResult(
                url=base,
                final_url=landing,
                status_code=200,
                html="<html></html>",
                content_type="text/html",
            ),
            next_page: html_page(next_page),
        }
    )
    extractor = RelativeLinkExtractor()
    engine = CrawlEngine(
        http_client=http,
        link_extractor=extractor,
        robots_checker=None,
        config=CrawlConfig(max_pages=2),
    )

    reports = await collect(engine, base)

    assert next_page in http.fetched_urls
    assert any(next_page in report.links for report in reports)
    assert extractor.base_urls == [landing, next_page]


class BlockingHttpClient(FakeHttpClient):
    def __init__(self) -> None:
        super().__init__({})
        self.started = asyncio.Event()
        self.cancelled = asyncio.Event()

    async def fetch(self, url: str) -> FetchResult:
        self.started.set()
        try:
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            self.cancelled.set()
            raise
        return FetchResult(url=url, status_code=200, html="", content_type="text/html")


@pytest.mark.asyncio
async def test_cancelling_crawl_cancels_active_workers() -> None:
    http = BlockingHttpClient()
    engine = CrawlEngine(
        http_client=http,
        link_extractor=FakeLinkExtractor({}),
        robots_checker=None,
        config=CrawlConfig(max_concurrency=2, max_pages=1),
    )

    async def consume() -> None:
        async for _report in engine.crawl("http://example.com/"):
            pass

    consumer = asyncio.create_task(consume())
    await http.started.wait()
    consumer.cancel()
    with pytest.raises(asyncio.CancelledError):
        await consumer

    assert http.cancelled.is_set()
