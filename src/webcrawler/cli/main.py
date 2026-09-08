"""CLI entry point: the composition root wiring adapters into the core engine."""

from __future__ import annotations

import argparse
import asyncio
import sys

import httpx

from webcrawler.adapters.bs4_link_extractor import BeautifulSoupLinkExtractor
from webcrawler.adapters.httpx_client import HttpxHttpClient
from webcrawler.adapters.robots_urllib import RobotsTxtChecker
from webcrawler.adapters.stdout_sink import StdoutSink
from webcrawler.core.crawl_engine import CrawlEngine
from webcrawler.core.models import CrawlConfig
from webcrawler.ports.output_sink import OutputSink
from webcrawler.ports.robots_checker import RobotsChecker


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def positive_float(value: str) -> float:
    parsed = float(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than zero")
    return parsed


def nonnegative_float(value: str) -> float:
    parsed = float(value)
    if parsed < 0:
        raise argparse.ArgumentTypeError("must not be negative")
    return parsed


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="webcrawler",
        description=(
            "Crawl a website starting from a base URL, printing each page's "
            "URL followed by every link found on it."
        ),
    )
    parser.add_argument("base_url", help="The base URL to start crawling from.")
    parser.add_argument(
        "--max-concurrency",
        type=positive_int,
        default=10,
        help="Maximum number of concurrent in-flight requests (default: 10).",
    )
    parser.add_argument(
        "--timeout",
        type=positive_float,
        default=10.0,
        help="Per-request timeout in seconds (default: 10.0).",
    )
    parser.add_argument(
        "--max-pages",
        type=positive_int,
        default=100,
        help="Maximum number of pages to fetch during the crawl (default: 100).",
    )
    parser.add_argument(
        "--delay",
        type=nonnegative_float,
        default=0.0,
        help="Delay in seconds after each request, per worker, for politeness (default: 0).",
    )
    parser.add_argument(
        "--no-robots",
        action="store_true",
        help="Disable robots.txt checking (enabled by default).",
    )
    parser.add_argument(
        "--user-agent",
        default="webcrawler/0.1",
        help="User-Agent header sent with requests (default: webcrawler/0.1).",
    )
    return parser


async def run(args: argparse.Namespace, sink: OutputSink) -> int:
    config = CrawlConfig(
        max_concurrency=args.max_concurrency,
        request_timeout=args.timeout,
        max_pages=args.max_pages,
        delay=args.delay,
        respect_robots=not args.no_robots,
        user_agent=args.user_agent,
    )

    async with HttpxHttpClient(
        timeout=config.request_timeout, user_agent=config.user_agent
    ) as http_client:
        robots_checker: RobotsChecker | None = None
        if config.respect_robots:
            robots_client = httpx.AsyncClient(
                timeout=config.request_timeout, headers={"User-Agent": config.user_agent}
            )
            robots_checker = RobotsTxtChecker(robots_client, timeout=config.request_timeout)

        engine = CrawlEngine(
            http_client=http_client,
            link_extractor=BeautifulSoupLinkExtractor(),
            robots_checker=robots_checker,
            config=config,
        )

        exit_code = 0
        try:
            async for report in engine.crawl(args.base_url):
                sink.emit(report)
        except ValueError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            exit_code = 1
        finally:
            if isinstance(robots_checker, RobotsTxtChecker):
                await robots_checker.aclose()

        return exit_code


def main() -> None:
    parser = build_arg_parser()
    args = parser.parse_args()
    sink = StdoutSink()
    exit_code = asyncio.run(run(args, sink))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
