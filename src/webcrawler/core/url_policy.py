"""Pure URL logic: normalization, domain matching, and link resolution.

This module has no I/O and no third-party dependencies beyond the stdlib,
so it can be unit tested in isolation from the rest of the crawler.
"""

from __future__ import annotations

from urllib.parse import urldefrag, urljoin, urlparse, urlunparse

#: Link schemes that are never crawlable / fetchable.
NON_CRAWLABLE_SCHEMES = frozenset({"mailto", "tel", "javascript", "data", "ftp"})

#: Schemes we are willing to fetch over HTTP(S).
FETCHABLE_SCHEMES = frozenset({"http", "https"})


def normalize_url(url: str) -> str:
    """Normalize a URL so that superficially-different equivalents compare equal.

    Normalization performed:
    - Lowercase scheme and host.
    - Strip URL fragments (``#section``).
    - Strip a single trailing slash from the path (except the root ``/``).
    - Drop default ports (``:80`` for http, ``:443`` for https).

    Query strings are intentionally left untouched -- see README for why.
    """
    url, _fragment = urldefrag(url)
    parsed = urlparse(url)

    scheme = parsed.scheme.lower()
    hostname = (parsed.hostname or "").lower()

    port = parsed.port
    default_port = {"http": 80, "https": 443}.get(scheme)
    netloc = hostname
    if port is not None and port != default_port:
        netloc = f"{hostname}:{port}"

    path = parsed.path
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    if path == "":
        path = "/"

    normalized = urlunparse((scheme, netloc, path, parsed.params, parsed.query, ""))
    return normalized


def resolve_link(base_url: str, href: str) -> str:
    """Resolve a possibly-relative ``href`` found on ``base_url`` into an absolute URL."""
    return urljoin(base_url, href)


def get_scheme(url: str) -> str:
    """Return the lowercase scheme of a URL, e.g. 'http', 'mailto'."""
    return urlparse(url).scheme.lower()


def is_crawlable_scheme(url: str) -> bool:
    """Return True if the URL uses a scheme we can fetch over HTTP(S)."""
    return get_scheme(url) in FETCHABLE_SCHEMES


def get_hostname(url: str) -> str | None:
    """Return the lowercase hostname of a URL, or None if it has none."""
    hostname = urlparse(url).hostname
    return hostname.lower() if hostname else None


def is_same_host(url: str, base_hostname: str) -> bool:
    """Return True if ``url``'s hostname exactly matches ``base_hostname``.

    This is an exact-match policy: subdomains do NOT match. For example, if
    ``base_hostname`` is ``example.com``, then ``blog.example.com`` is
    considered a different host and will not match.
    """
    hostname = get_hostname(url)
    return hostname is not None and hostname == base_hostname.lower()
