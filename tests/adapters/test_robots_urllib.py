import asyncio

import httpx
import pytest
import respx

from webcrawler.adapters.robots_urllib import RobotsTxtChecker

ROBOTS_TXT = """
User-agent: *
Disallow: /private/
Allow: /
"""


@pytest.mark.asyncio
async def test_allows_unrestricted_path() -> None:
    with respx.mock:
        respx.get("http://example.com/robots.txt").mock(
            return_value=httpx.Response(200, text=ROBOTS_TXT)
        )
        async with httpx.AsyncClient() as client:
            checker = RobotsTxtChecker(client)
            allowed = await checker.is_allowed("http://example.com/public", "test-agent")

    assert allowed is True


@pytest.mark.asyncio
async def test_disallows_restricted_path() -> None:
    with respx.mock:
        respx.get("http://example.com/robots.txt").mock(
            return_value=httpx.Response(200, text=ROBOTS_TXT)
        )
        async with httpx.AsyncClient() as client:
            checker = RobotsTxtChecker(client)
            allowed = await checker.is_allowed("http://example.com/private/secret", "test-agent")

    assert allowed is False


@pytest.mark.asyncio
async def test_defaults_to_allow_when_robots_txt_missing() -> None:
    with respx.mock:
        respx.get("http://example.com/robots.txt").mock(return_value=httpx.Response(404))
        async with httpx.AsyncClient() as client:
            checker = RobotsTxtChecker(client)
            allowed = await checker.is_allowed("http://example.com/anything", "test-agent")

    assert allowed is True


@pytest.mark.asyncio
async def test_caches_parser_per_origin() -> None:
    with respx.mock:
        route = respx.get("http://example.com/robots.txt").mock(
            return_value=httpx.Response(200, text=ROBOTS_TXT)
        )
        async with httpx.AsyncClient() as client:
            checker = RobotsTxtChecker(client)
            await checker.is_allowed("http://example.com/a", "test-agent")
            await checker.is_allowed("http://example.com/b", "test-agent")

    assert route.call_count == 1


@pytest.mark.asyncio
async def test_deduplicates_concurrent_robots_requests() -> None:
    async def delayed_response(_request: httpx.Request) -> httpx.Response:
        await asyncio.sleep(0.01)
        return httpx.Response(200, text=ROBOTS_TXT)

    with respx.mock:
        route = respx.get("http://example.com/robots.txt").mock(side_effect=delayed_response)
        async with httpx.AsyncClient() as client:
            checker = RobotsTxtChecker(client)
            results = await asyncio.gather(
                *[
                    checker.is_allowed(f"http://example.com/page-{index}", "test-agent")
                    for index in range(10)
                ]
            )

    assert results == [True] * 10
    assert route.call_count == 1
