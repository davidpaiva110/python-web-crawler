import argparse

import pytest

from webcrawler.cli.main import build_arg_parser, run
from webcrawler.core.models import PageReport


class FakeSink:
    def __init__(self) -> None:
        self.reports: list[PageReport] = []

    def emit(self, report: PageReport) -> None:
        self.reports.append(report)


class TestArgParsing:
    def test_requires_base_url(self) -> None:
        parser = build_arg_parser()
        with pytest.raises(SystemExit):
            parser.parse_args([])

    def test_parses_defaults(self) -> None:
        parser = build_arg_parser()
        args = parser.parse_args(["http://example.com"])
        assert args.base_url == "http://example.com"
        assert args.max_concurrency == 10
        assert args.timeout == 10.0
        assert args.max_pages == 100
        assert args.delay == 0.0
        assert args.no_robots is False

    def test_parses_custom_flags(self) -> None:
        parser = build_arg_parser()
        args = parser.parse_args(
            [
                "http://example.com",
                "--max-concurrency",
                "5",
                "--timeout",
                "3.5",
                "--max-pages",
                "10",
                "--delay",
                "0.5",
                "--no-robots",
            ]
        )
        assert args.max_concurrency == 5
        assert args.timeout == 3.5
        assert args.max_pages == 10
        assert args.delay == 0.5
        assert args.no_robots is True

    @pytest.mark.parametrize(
        "option",
        [
            "--max-concurrency",
            "--timeout",
            "--max-pages",
            "--delay",
        ],
    )
    def test_rejects_invalid_numeric_options(self, option: str) -> None:
        parser = build_arg_parser()
        value = "-1" if option == "--delay" else "0"

        with pytest.raises(SystemExit):
            parser.parse_args(["http://example.com", option, value])


@pytest.mark.asyncio
async def test_run_reports_invalid_url_error() -> None:
    args = argparse.Namespace(
        base_url="not-a-valid-url-without-host",
        max_concurrency=1,
        timeout=1.0,
        max_pages=1,
        delay=0.0,
        no_robots=True,
        user_agent="test-agent",
    )
    sink = FakeSink()
    exit_code = await run(args, sink)
    assert exit_code == 1
    assert sink.reports == []
