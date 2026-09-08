"""HTML link extraction adapter using BeautifulSoup with the lxml parser."""

from __future__ import annotations

from bs4 import BeautifulSoup

from webcrawler.core.url_policy import resolve_link
from webcrawler.ports.link_extractor import LinkExtractor as LinkExtractorPort


class BeautifulSoupLinkExtractor(LinkExtractorPort):
    """Extracts and resolves all ``<a href>`` links from an HTML document."""

    def extract_links(self, base_url: str, html: str) -> list[str]:
        soup = BeautifulSoup(html, "lxml")
        links: list[str] = []
        for anchor in soup.find_all("a", href=True):
            href = str(anchor["href"]).strip()
            if not href:
                continue
            links.append(resolve_link(base_url, href))
        return links
