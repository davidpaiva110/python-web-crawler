# webcrawler

A small asynchronous web crawler for crawling pages on a single hostname.

The crawler starts from a URL, follows HTTP(S) links on the exact same
hostname, avoids fetching duplicate URLs, checks `robots.txt` by default, and
streams each completed page and its discovered links to the terminal.

## Requirements

- Python 3.10+
- [Poetry](https://python-poetry.org/)

## Installation

```bash
poetry install
```

## Usage

```bash
poetry run webcrawler https://example.com
```

Example with configuration:

```bash
poetry run webcrawler https://example.com \
    --max-concurrency 10 \
    --timeout 10 \
    --max-pages 100 \
    --delay 0.1
```

Disable `robots.txt` checks when needed:

```bash
poetry run webcrawler https://example.com --no-robots
```

### Options

| Option | Default | Description |
|---|---:|---|
| `base_url` | required | URL where crawling starts |
| `--max-concurrency` | `10` | Maximum number of concurrent requests |
| `--timeout` | `10.0` | Request timeout in seconds |
| `--max-pages` | `100` | Maximum number of pages to fetch |
| `--delay` | `0` | Delay after processing each URL, per worker, in seconds |
| `--no-robots` | disabled | Disable `robots.txt` checks |
| `--user-agent` | `webcrawler/0.1` | User-Agent sent with requests |

## Output

Results are printed as pages complete:

```text
https://example.com/
  https://iana.org/domains/example

```

Relative links are converted to absolute URLs before they are reported. Links
to other domains, subdomains, or non-crawlable schemes are still printed when
found, but are not followed. For example, a `tel:` or `mailto:` link appears
in the output but never becomes an HTTP request. Links are extracted only from
responses with an HTML content type and a status below 400. The HTML parser
tolerates many malformed documents; if link extraction raises an exception,
the failure is reported for that page and the crawl continues.

The crawler distinguishes between discovered URLs and crawlable URLs. For
example:

- `https://example.com/about` — reported and crawled
- `https://example.com/about#team` — normalized and deduplicated
- `https://blog.example.com` — reported but not crawled
- `mailto:user@example.com` — reported but not crawled
- `tel:+35315339837` — reported but not crawled

HTTPX follows redirects before the crawler receives the response. The crawler
then checks that the final response hostname still matches the starting
hostname. A redirect to another host is reported and its HTML is not parsed,
although the redirect request itself has already been made by HTTPX.

## Project structure

```text
crawler/
├── pyproject.toml              # Poetry configuration and dependencies
├── README.md
├── copilot-prompt.md           # Original project requirements
├── src/
│   └── webcrawler/
│       ├── cli/
│       │   └── main.py         # CLI arguments and dependency wiring
│       ├── core/
│       │   ├── crawl_engine.py # Crawl orchestration and concurrency
│       │   ├── models.py       # Crawl data models
│       │   └── url_policy.py   # URL normalization and host rules
│       ├── ports/
│       │   ├── http_client.py  # HTTP client interface
│       │   ├── link_extractor.py
│       │   ├── output_sink.py
│       │   └── robots_checker.py
│       └── adapters/
│           ├── httpx_client.py # HTTP adapter using HTTPX
│           ├── bs4_link_extractor.py
│           ├── robots_urllib.py
│           └── stdout_sink.py  # Terminal output adapter
└── tests/
    ├── core/
    ├── adapters/
    ├── cli/
    └── fixtures/
```

### Architecture

The project uses a small ports-and-adapters structure:

- `core` contains the crawling algorithm, URL rules, and data models.
- `ports` define interfaces for HTTP, link extraction, robots checks, and
  output.
- `adapters` implement those interfaces using HTTPX, BeautifulSoup,
  `urllib.robotparser`, and stdout.
- `cli/main.py` is the composition root that connects the concrete adapters
  to the core engine.

The core depends on interfaces rather than concrete libraries. This allows the
HTTP client, HTML parser, or output format to be replaced without changing
the crawl algorithm. It also allows the engine to be tested with simple fake
ports instead of a real network.

Because the core depends on ports rather than the CLI or concrete adapters,
the current in-memory frontier and terminal output can later be replaced with
persistent storage and an API without changing the core crawling algorithm.
This keeps future additions, such as resumable crawls or service-based access,
localized to new adapters and application wiring.

### Design decisions

| Decision | Reason |
|---|---|
| `asyncio` | Crawling is mainly I/O-bound, so requests can overlap while waiting for responses. |
| `asyncio.Queue` | Links are discovered dynamically while pages are processed. |
| In-memory visited set | Fast deduplication is sufficient for a bounded, single-process CLI. |
| Exact hostname matching | Prevents crawling subdomains and external domains. |
| Retries with backoff | Helps recover from temporary network and server failures without retrying forever. |
| Ports and adapters | Keeps infrastructure replaceable and makes the core easy to test. |

## How crawling works

The crawler uses `asyncio` workers and an in-memory `asyncio.Queue` as the URL
frontier:

`asyncio` is a good fit because crawling is mainly an I/O-bound task: workers
spend most of their time waiting for HTTP responses. While one request waits,
another worker can make progress without creating a thread for every request.
The queue is used because links are discovered while pages are being processed,
so the complete list of URLs is not known at the start. It gives workers a
shared frontier, while `--max-concurrency` limits the number of requests in
flight and the visited set prevents duplicate work.

1. The starting URL is added to the frontier.
2. Workers fetch URLs concurrently, up to `--max-concurrency`.
3. HTML links are extracted and resolved to absolute URLs.
4. Normalized same-host HTTP(S) URLs are added to the frontier if they have not
   already been seen.
5. A report is emitted as soon as a worker finishes processing a page.

The `visited` set prevents duplicate requests. `--max-pages` bounds the crawl
and provides a basic safeguard against URL-generated crawler traps. Output
order is completion order, not guaranteed discovery order.

The numeric options are validated before crawling: concurrency, page count,
and timeout must be greater than zero, while delay may be zero but not
negative.

## URL and robots rules

Before deduplication, URLs are normalized by:

- Lowercasing the scheme and hostname
- Removing fragments such as `#section`
- Representing an empty path as `/`
- Removing trailing slashes from non-root paths
- Removing default HTTP and HTTPS ports

Query strings are preserved because different query strings can represent
different resources. The crawler follows only URLs whose hostname exactly
matches the starting hostname. For example, `blog.example.com` is not
followed when the starting hostname is `example.com`.

Only `http` and `https` links are crawlable. `mailto:`, `tel:`,
`javascript:`, `data:`, and `ftp:` links are not fetched, although they can be
reported as discovered links.

`robots.txt` is checked by default through the `RobotsChecker` port and its
`RobotsTxtChecker` adapter. Rules are cached per origin during a crawl. If the
robots file is unavailable or returns an error, the current implementation
allows the request. Pass `--no-robots` to skip robots checks entirely.

Timeouts, connection/network errors, and HTTP `408`, `429`, `500`, `502`,
`503`, and `504` responses are retried up to three total attempts. The adapter
waits `0.1` seconds before the second attempt and `0.2` seconds before the
third attempt. Permanent client errors are returned immediately.

## Dependencies

Runtime dependencies:

- [HTTPX](https://www.python-httpx.org/) for asynchronous HTTP requests
- [BeautifulSoup](https://www.crummy.com/software/BeautifulSoup/) for HTML
  parsing
- [lxml](https://lxml.de/) as the BeautifulSoup parser backend

Development dependencies include `pytest`, `pytest-asyncio`, `respx`, `ruff`,
and `mypy`. Dependencies like Scrapy and Playwright are not used.

## Testing and quality checks

```bash
poetry run pytest
poetry run ruff check .
poetry run ruff format --check .
poetry run mypy src
```

The tests cover URL rules, relative link extraction, crawl orchestration,
deduplication, host restrictions, non-HTML responses, HTTP failures,
`robots.txt`, page limits, adapter behavior, and CLI parsing. Network behavior
is tested through fakes or mocked HTTP transport rather than real websites.

The HTTP adapter makes up to three total attempts for transient timeouts,
network errors, and the temporary HTTP responses listed above. Retries use
`0.1`- and `0.2`-second exponential backoff delays. Permanent client errors
are returned immediately, and a page still produces only one crawl report
after the retry attempts are exhausted.

## Limitations and possible improvements

This is a single-process, single-run crawler. It does not currently provide:

- JavaScript rendering
- Authentication or cookies
- Persistent or resumable crawl state
- Sitemap discovery or depth limits
- Adaptive rate limiting
- Content-based duplicate detection
- Multiple-domain crawling
- Structured output storage

For a larger crawler, a persistent frontier, per-host politeness rules, and a
background service or API would be more appropriate than one CLI process.

## References

The design was informed by these sources:

- [ByteByteGo: Design a Web Crawler](https://bytebytego.com/courses/system-design-interview/design-a-web-crawler) — URL frontiers, deduplication, and politeness.
- [HelloInterview: Web Crawler](https://www.hellointerview.com/learn/system-design/problem-breakdowns/web-crawler) — the fetch, parse, extract, and enqueue flow.
- [Octoparse: How to Build a Web Crawler](https://www.octoparse.com/blog/how-to-build-a-web-crawler-from-scratch-a-guide-for-beginners) — beginner-friendly visited-set and same-domain techniques.
- [dev.to: Build a Web Crawler from Scratch](https://dev.to/thectogeneral/build-a-web-crawler-from-scratch-34on) — basic crawling and response content handling.


## Development Setup

The project was developed with PyCharm and GitHub Copilot using the
`GPT-5.6 Luna` model. Copilot was used as an interactive development
assistant for implementation ideas, Python and asyncio suggestions, and test
ideas. Suggestions were reviewed and adapted manually, then verified with
the project test suite, Ruff, and mypy. The original requirements are
preserved in `copilot-prompt.md`.

## Author's note

I am a software engineer working primarily with Java and Scala. I chose
Python for this project as an opportunity to learn another language, with
support from GitHub Copilot, while maintaining a focus on producing clear,
well-tested code.

