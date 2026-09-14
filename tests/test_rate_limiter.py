"""Per-host politeness: minimum interval, 429/503 backoff, decay."""

import time

from crawler import Crawler, _RateLimiter
from tests.fake_http import FakeSite, page

BASE = "https://example.com"


class _FakeRobots:
    def __init__(self, delay):
        self._delay = delay

    def crawl_delay(self, user_agent):
        return self._delay

    def can_fetch(self, user_agent, url):
        return True


def test_rate_limiter_spaces_requests_by_minimum_interval():
    rl = _RateLimiter(min_interval=0.05)
    t0 = time.monotonic()
    rl.acquire()
    rl.acquire()
    rl.acquire()
    assert time.monotonic() - t0 >= 0.10


def test_rate_limiter_with_zero_interval_does_not_block():
    rl = _RateLimiter(min_interval=0)
    t0 = time.monotonic()
    for _ in range(20):
        rl.acquire()
    assert time.monotonic() - t0 < 0.05


def test_rate_limiter_doubles_interval_after_429():
    rl = _RateLimiter(min_interval=0.1)
    rl.on_response(429)
    assert rl.interval == 0.2


def test_rate_limiter_backs_off_on_503_too():
    rl = _RateLimiter(min_interval=0.1)
    rl.on_response(503)
    assert rl.interval == 0.2


def test_rate_limiter_backoff_applies_floor_when_baseline_is_zero():
    rl = _RateLimiter(min_interval=0)
    rl.on_response(429)
    assert rl.interval > 0


def test_rate_limiter_backoff_is_capped():
    rl = _RateLimiter(min_interval=0.5)
    for _ in range(20):
        rl.on_response(429)
    assert rl.interval <= _RateLimiter._BACKOFF_CAP


def test_rate_limiter_decays_toward_baseline_after_sustained_success():
    rl = _RateLimiter(min_interval=0.1)
    rl.on_response(429)
    for _ in range(_RateLimiter._DECAY_AFTER):
        rl.on_response(200)
    assert rl.interval == 0.1


def test_rate_limiter_never_decays_below_baseline():
    rl = _RateLimiter(min_interval=0.1)
    for _ in range(50):
        rl.on_response(200)
    assert rl.interval == 0.1


def test_crawler_shares_one_limiter_across_workers():
    pages = {BASE: page(links=[f"/p{i}" for i in range(4)])}
    for i in range(4):
        pages[f"{BASE}/p{i}"] = page()
    site = FakeSite(pages)
    c = Crawler(BASE, respect_robots=False, delay=0.05, max_workers=4, max_pages=100)
    c.session.get = site.get
    t0 = time.monotonic()
    list(c.crawl())
    # 5 pages at a 0.05s shared minimum interval -> at least 4 gaps
    assert time.monotonic() - t0 >= 0.20


def test_robots_crawl_delay_raises_the_minimum_interval():
    c = Crawler(BASE, respect_robots=False, delay=0.1)
    c._apply_robots_delay(_FakeRobots(0.4))
    assert c.limiter.baseline == 0.4


def test_robots_crawl_delay_does_not_lower_configured_delay():
    c = Crawler(BASE, respect_robots=False, delay=0.5)
    c._apply_robots_delay(_FakeRobots(0.1))
    assert c.limiter.baseline == 0.5


def test_missing_robots_crawl_delay_leaves_interval_alone():
    c = Crawler(BASE, respect_robots=False, delay=0.2)
    c._apply_robots_delay(_FakeRobots(None))
    assert c.limiter.baseline == 0.2
