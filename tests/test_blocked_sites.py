"""Bot-wall and robots.txt failures must surface, not silently empty the crawl."""

from crawler import CHALLENGE_ERROR, Crawler
from tests.fake_http import FakeResponse

BASE = "https://example.com"
ROBOTS = f"{BASE}/robots.txt"

_CHALLENGE_HEADERS = {
    "content-type": "text/html; charset=UTF-8",
    "cf-mitigated": "challenge",
}
_HTML = {"content-type": "text/html; charset=utf-8"}


def _stub(routes, calls=None):
    """session.get stand-in: routes maps url -> FakeResponse."""
    def get(url, headers=None, **kwargs):
        if calls is not None:
            calls.append(url)
        return routes.get(url) or FakeResponse(url, 404, {"content-type": "text/plain"}, "")
    return get


def _crawler_with_robots(routes, calls=None, **kw):
    kw.setdefault("delay", 0)
    c = Crawler(BASE, respect_robots=False, **kw)
    c.session.get = _stub(routes, calls)
    c._load_robots(BASE)
    return c


# ── Cloudflare challenge on pages ───────────────────────────────────────────

def test_challenged_page_is_reported_as_blocked():
    challenge_html = '<html><body><a href="/cdn-cgi/x">x</a></body></html>'
    c = Crawler(BASE, respect_robots=False, delay=0)
    c.session.get = _stub({BASE: FakeResponse(BASE, 403, _CHALLENGE_HEADERS, challenge_html)})

    pages = [p for p, _, _ in c.crawl()]

    assert len(pages) == 1
    assert pages[0].status_code == 403
    assert pages[0].error == CHALLENGE_ERROR
    # The interstitial's own links are not the site's — don't follow them.
    assert pages[0].internal_links == []


def test_plain_403_is_not_mistaken_for_a_challenge():
    c = Crawler(BASE, respect_robots=False, delay=0)
    c.session.get = _stub({BASE: FakeResponse(BASE, 403, _HTML, "<html></html>")})

    pages = [p for p, _, _ in c.crawl()]

    assert pages[0].error is None


# ── robots.txt fetching ─────────────────────────────────────────────────────

def test_robots_is_fetched_through_the_crawler_session():
    calls = []
    routes = {ROBOTS: FakeResponse(ROBOTS, 200, {"content-type": "text/plain"},
                                   "User-agent: *\nDisallow: /private/\n")}
    c = _crawler_with_robots(routes, calls)

    assert calls == [ROBOTS]
    assert c._can_fetch(f"{BASE}/public")
    assert not c._can_fetch(f"{BASE}/private/page")
    assert c.warnings == []


def test_robots_follows_redirect_to_www_host():
    www_robots = "https://www.example.com/robots.txt"
    routes = {ROBOTS: FakeResponse(www_robots, 200, {"content-type": "text/plain"},
                                   "User-agent: *\nDisallow: /x/\n",
                                   history_urls=[ROBOTS])}
    c = _crawler_with_robots(routes)

    assert c._can_fetch(f"{BASE}/ok")
    assert not c._can_fetch(f"{BASE}/x/y")


def test_robots_403_blocks_everything_and_warns():
    routes = {ROBOTS: FakeResponse(ROBOTS, 403, {"content-type": "text/plain"}, "Forbidden")}
    c = _crawler_with_robots(routes)

    assert not c._can_fetch(f"{BASE}/anything")
    assert len(c.warnings) == 1
    assert "403" in c.warnings[0]


def test_robots_behind_challenge_is_ignored_with_a_warning():
    # A bot wall is not the site's crawl policy; let the page fetches report
    # the block instead of pretending robots.txt disallowed everything.
    routes = {ROBOTS: FakeResponse(ROBOTS, 403, _CHALLENGE_HEADERS, "<html></html>")}
    c = _crawler_with_robots(routes)

    assert c._can_fetch(f"{BASE}/anything")
    assert len(c.warnings) == 1
    assert "Cloudflare" in c.warnings[0]


def test_missing_robots_allows_everything_without_warning():
    c = _crawler_with_robots({})

    assert c._can_fetch(f"{BASE}/anything")
    assert c.warnings == []


def test_robots_server_error_crawls_without_robots_and_warns():
    routes = {ROBOTS: FakeResponse(ROBOTS, 503, {"content-type": "text/plain"}, "")}
    c = _crawler_with_robots(routes)

    assert c._can_fetch(f"{BASE}/anything")
    assert len(c.warnings) == 1
