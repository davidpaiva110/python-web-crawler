from webcrawler.core.url_policy import (
    get_hostname,
    is_crawlable_scheme,
    is_same_host,
    normalize_url,
    resolve_link,
)


class TestNormalizeUrl:
    def test_strips_fragment(self) -> None:
        assert normalize_url("http://example.com/page#section") == "http://example.com/page"

    def test_lowercases_scheme_and_host(self) -> None:
        assert normalize_url("HTTP://Example.COM/Page") == "http://example.com/Page"

    def test_strips_trailing_slash(self) -> None:
        assert normalize_url("http://example.com/page/") == "http://example.com/page"

    def test_keeps_root_slash(self) -> None:
        assert normalize_url("http://example.com/") == "http://example.com/"
        assert normalize_url("http://example.com") == "http://example.com/"

    def test_drops_default_port(self) -> None:
        assert normalize_url("http://example.com:80/page") == "http://example.com/page"
        assert normalize_url("https://example.com:443/page") == "https://example.com/page"

    def test_keeps_non_default_port(self) -> None:
        assert normalize_url("http://example.com:8080/page") == "http://example.com:8080/page"

    def test_preserves_query_string(self) -> None:
        assert normalize_url("http://example.com/page?a=1") == "http://example.com/page?a=1"

    def test_equivalent_urls_normalize_identically(self) -> None:
        a = normalize_url("HTTP://Example.com:80/page/#frag")
        b = normalize_url("http://example.com/page")
        assert a == b


class TestResolveLink:
    def test_resolves_relative_path(self) -> None:
        assert resolve_link("http://example.com/dir/", "page.html") == (
            "http://example.com/dir/page.html"
        )

    def test_resolves_absolute_path(self) -> None:
        assert resolve_link("http://example.com/dir/x", "/other") == "http://example.com/other"

    def test_resolves_protocol_relative(self) -> None:
        assert resolve_link("http://example.com/", "//other.com/x") == "http://other.com/x"


class TestSchemeChecks:
    def test_mailto_is_not_crawlable(self) -> None:
        assert not is_crawlable_scheme("mailto:foo@example.com")

    def test_tel_is_not_crawlable(self) -> None:
        assert not is_crawlable_scheme("tel:+1234567890")

    def test_javascript_is_not_crawlable(self) -> None:
        assert not is_crawlable_scheme("javascript:void(0)")

    def test_http_is_crawlable(self) -> None:
        assert is_crawlable_scheme("http://example.com")

    def test_https_is_crawlable(self) -> None:
        assert is_crawlable_scheme("https://example.com")


class TestHostMatching:
    def test_get_hostname(self) -> None:
        assert get_hostname("http://Example.COM/page") == "example.com"

    def test_same_host_matches(self) -> None:
        assert is_same_host("http://example.com/page", "example.com")

    def test_different_domain_does_not_match(self) -> None:
        assert not is_same_host("http://other.com/page", "example.com")

    def test_subdomain_does_not_match(self) -> None:
        assert not is_same_host("http://blog.example.com/page", "example.com")

    def test_case_insensitive_match(self) -> None:
        assert is_same_host("http://EXAMPLE.com/page", "example.com")
