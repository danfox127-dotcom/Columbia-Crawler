"""Rolling-window parallel crawl behaviour."""

import threading
import time

from crawler import Crawler, PageData
from tests.fake_http import FakeSite, page

BASE = "https://example.com"


def _graph(n):
    """Hub page linking to n leaf pages."""
    pages = {f"{BASE}": page(links=[f"/p{i}" for i in range(n)])}
    for i in range(n):
        pages[f"{BASE}/p{i}"] = page()
    return pages


def _crawler(site, **kw):
    kw.setdefault("respect_robots", False)
    kw.setdefault("delay", 0)
    kw.setdefault("max_pages", 100)
    c = Crawler(BASE, **kw)
    c.session.get = site.get
    return c


def test_parallel_crawl_visits_every_reachable_page_exactly_once():
    site = FakeSite(_graph(12))
    c = _crawler(site, max_workers=8)
    urls = [p.url for p, _, _ in c.crawl()]
    assert len(urls) == len(set(urls)) == 13
    assert sorted(urls) == sorted(_graph(12).keys())


def test_parallel_crawl_respects_max_pages_exactly():
    site = FakeSite(_graph(30))
    c = _crawler(site, max_workers=8, max_pages=7)
    pages = list(c.crawl())
    assert len(pages) == 7
    # never over-fetch past the cap, even mid-window
    assert len(site.urls_requested) == 7


def test_parallel_crawl_keeps_multiple_requests_in_flight():
    site = FakeSite(_graph(16), latency=0.05)
    c = _crawler(site, max_workers=8)
    list(c.crawl())
    assert site.max_in_flight > 1


def test_single_worker_crawl_is_serial():
    site = FakeSite(_graph(6), latency=0.01)
    c = _crawler(site, max_workers=1)
    list(c.crawl())
    assert site.max_in_flight == 1


def test_slow_page_does_not_block_other_pages():
    gate = threading.Event()
    pages = _graph(4)
    pages[f"{BASE}/p0"] = page(gate=gate)
    site = FakeSite(pages)
    c = _crawler(site, max_workers=4)

    seen = []
    for p, _, _ in c.crawl():
        seen.append(p.url)
        if len(seen) == 3:      # hub + two fast leaves got through first
            gate.set()

    assert f"{BASE}/p0" not in seen[:3], f"blocked page stalled the window: {seen}"
    assert len(seen) == 5


def test_progress_counts_advance_with_yields():
    site = FakeSite(_graph(5))
    c = _crawler(site, max_workers=4)
    dones = [done for _, done, _ in c.crawl()]
    assert dones == [1, 2, 3, 4, 5, 6]


def test_worker_exception_is_reported_as_error_page_and_crawl_continues():
    site = FakeSite(_graph(3))
    c = _crawler(site, max_workers=2)
    original = c._fetch

    def boom(url):
        if url == f"{BASE}/p1":
            raise RuntimeError("worker exploded")
        return original(url)

    c._fetch = boom
    results = {p.url: p for p, _, _ in c.crawl()}
    assert len(results) == 4
    failed = results[f"{BASE}/p1"]
    assert failed.status_code == 0
    assert "worker exploded" in (failed.error or "")


def test_seed_visited_pages_are_not_refetched():
    site = FakeSite(_graph(3))
    c = _crawler(site, max_workers=4, seed_visited={f"{BASE}/p1"})
    urls = [p.url for p, _, _ in c.crawl()]
    assert f"{BASE}/p1" not in urls
    assert f"{BASE}/p1" not in site.urls_requested
