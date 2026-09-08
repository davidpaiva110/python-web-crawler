from pathlib import Path

from webcrawler.adapters.bs4_link_extractor import BeautifulSoupLinkExtractor

FIXTURES = Path(__file__).parent.parent / "fixtures"


def read_fixture(name: str) -> str:
    return (FIXTURES / name).read_text()


class TestBeautifulSoupLinkExtractor:
    def setup_method(self) -> None:
        self.extractor = BeautifulSoupLinkExtractor()

    def test_extracts_and_resolves_links(self) -> None:
        html = read_fixture("home.html")
        links = self.extractor.extract_links("http://example.com/", html)

        assert "http://example.com/about" in links
        assert "http://example.com/page2.html" in links
        assert "https://other-domain.com/x" in links
        assert "http://blog.example.com/post" in links
        assert "mailto:someone@example.com" in links
        assert "tel:+15551234567" in links
        assert "javascript:void(0)" in links

    def test_ignores_anchors_without_href(self) -> None:
        html = "<html><body><a>no href</a></body></html>"
        links = self.extractor.extract_links("http://example.com/", html)
        assert links == []

    def test_handles_malformed_html_without_raising(self) -> None:
        html = read_fixture("malformed.html")
        links = self.extractor.extract_links("http://example.com/", html)
        assert "http://example.com/x" in links
