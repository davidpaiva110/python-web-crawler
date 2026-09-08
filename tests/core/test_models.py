import pytest

from webcrawler.core.models import CrawlConfig


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("max_concurrency", 0),
        ("max_concurrency", -1),
        ("max_pages", 0),
        ("max_pages", -1),
        ("request_timeout", 0.0),
        ("request_timeout", -1.0),
        ("delay", -0.1),
    ],
)
def test_rejects_invalid_configuration(field: str, value: int | float) -> None:
    with pytest.raises(ValueError):
        CrawlConfig(**{field: value})


def test_accepts_zero_delay() -> None:
    assert CrawlConfig(delay=0.0).delay == 0.0
