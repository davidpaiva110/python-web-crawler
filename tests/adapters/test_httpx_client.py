from unittest.mock import AsyncMock, call, patch

import httpx
import pytest
import respx

from webcrawler.adapters.httpx_client import HttpxHttpClient


@pytest.mark.asyncio
async def test_fetch_returns_html_and_status() -> None:
    url = "http://example.com/"
    with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(200, html="<html><body>hi</body></html>"))
        async with HttpxHttpClient(timeout=5.0, user_agent="test-agent") as client:
            result = await client.fetch(url)

    assert result.status_code == 200
    assert result.final_url == url
    assert result.html is not None
    assert "hi" in result.html
    assert result.error is None


@pytest.mark.asyncio
async def test_fetch_reports_timeout_as_error() -> None:
    url = "http://example.com/slow"
    with respx.mock:
        respx.get(url).mock(side_effect=httpx.TimeoutException("timed out"))
        with patch("webcrawler.adapters.httpx_client.asyncio.sleep", new_callable=AsyncMock):
            async with HttpxHttpClient(timeout=1.0, user_agent="test-agent") as client:
                result = await client.fetch(url)

    assert result.error == "Request timed out"


@pytest.mark.asyncio
async def test_fetch_reports_connection_error() -> None:
    url = "http://example.com/down"
    with respx.mock:
        respx.get(url).mock(side_effect=httpx.ConnectError("refused"))
        with patch("webcrawler.adapters.httpx_client.asyncio.sleep", new_callable=AsyncMock):
            async with HttpxHttpClient(timeout=1.0, user_agent="test-agent") as client:
                result = await client.fetch(url)

    assert result.error is not None
    assert "Connection error" in result.error


@pytest.mark.asyncio
async def test_fetch_skips_html_body_for_non_html_content_type() -> None:
    url = "http://example.com/image.png"
    with respx.mock:
        respx.get(url).mock(
            return_value=httpx.Response(
                200, content=b"binary", headers={"content-type": "image/png"}
            )
        )
        async with HttpxHttpClient(timeout=5.0, user_agent="test-agent") as client:
            result = await client.fetch(url)

    assert result.html is None
    assert result.content_type == "image/png"


@pytest.mark.asyncio
async def test_fetch_reports_4xx_status_without_error() -> None:
    url = "http://example.com/missing"
    with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(404, html="<html>not found</html>"))
        async with HttpxHttpClient(timeout=5.0, user_agent="test-agent") as client:
            result = await client.fetch(url)

    assert result.status_code == 404
    assert result.error is None


@pytest.mark.asyncio
async def test_fetch_retries_transient_status_then_succeeds() -> None:
    url = "http://example.com/retry"
    route_responses = [
        httpx.Response(503),
        httpx.Response(200, html="<html>ok</html>"),
    ]
    with respx.mock:
        route = respx.get(url).mock(side_effect=route_responses)
        with patch(
            "webcrawler.adapters.httpx_client.asyncio.sleep", new_callable=AsyncMock
        ) as sleep:
            async with HttpxHttpClient(timeout=5.0, user_agent="test-agent") as client:
                result = await client.fetch(url)

    assert route.call_count == 2
    assert result.status_code == 200
    assert result.error is None
    assert sleep.await_args_list == [call(0.1)]


@pytest.mark.asyncio
async def test_fetch_retries_timeout_then_succeeds() -> None:
    url = "http://example.com/retry-timeout"
    route_responses = [
        httpx.TimeoutException("timed out"),
        httpx.Response(200, html="<html>ok</html>"),
    ]
    with respx.mock:
        route = respx.get(url).mock(side_effect=route_responses)
        with patch("webcrawler.adapters.httpx_client.asyncio.sleep", new_callable=AsyncMock):
            async with HttpxHttpClient(timeout=5.0, user_agent="test-agent") as client:
                result = await client.fetch(url)

    assert route.call_count == 2
    assert result.status_code == 200


@pytest.mark.asyncio
async def test_fetch_returns_final_status_after_retry_limit() -> None:
    url = "http://example.com/unavailable"
    with respx.mock:
        route = respx.get(url).mock(return_value=httpx.Response(503))
        with patch(
            "webcrawler.adapters.httpx_client.asyncio.sleep", new_callable=AsyncMock
        ) as sleep:
            async with HttpxHttpClient(timeout=5.0, user_agent="test-agent") as client:
                result = await client.fetch(url)

    assert route.call_count == 3
    assert result.status_code == 503
    assert sleep.await_args_list == [call(0.1), call(0.2)]


@pytest.mark.asyncio
async def test_fetch_does_not_retry_non_transient_status() -> None:
    url = "http://example.com/missing"
    with respx.mock:
        route = respx.get(url).mock(return_value=httpx.Response(404))
        async with HttpxHttpClient(timeout=5.0, user_agent="test-agent") as client:
            result = await client.fetch(url)

    assert route.call_count == 1
    assert result.status_code == 404


@pytest.mark.asyncio
async def test_fetch_returns_final_url_after_redirect() -> None:
    url = "http://example.com/start"
    redirected = "http://example.com/final"
    with respx.mock:
        respx.get(url).mock(return_value=httpx.Response(302, headers={"location": redirected}))
        respx.get(redirected).mock(return_value=httpx.Response(200, html="<html>ok</html>"))
        async with HttpxHttpClient(timeout=5.0, user_agent="test-agent") as client:
            result = await client.fetch(url)

    assert result.status_code == 200
    assert result.final_url == redirected
