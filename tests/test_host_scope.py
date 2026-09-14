"""Which hosts count as "this site" — www variants and post-redirect hosts."""

from crawler import Crawler
from tests.fake_http import FakeSite, page

BASE = "https://example.com"
OTHER = "https://www2.example.org"


def _crawler(site, start=BASE, **kw):
    kw.setdefault("respect_robots", False)
    kw.setdefault("delay", 0)
    kw.setdefault("max_pages", 50)
    kw.setdefault("max_workers", 1)
    c = Crawler(start, **kw)
    c.session.get = site.get
    return c


def test_www_variant_of_start_host_is_internal():
    c = Crawler(BASE, respect_robots=False)
    assert c._same_domain("https://www.example.com/page") is True


def test_bare_host_is_internal_when_start_url_is_www():
    c = Crawler("https://www.example.com", respect_robots=False)
    assert c._same_domain("https://example.com/page") is True


def test_host_match_is_case_insensitive():
    c = Crawler(BASE, respect_robots=False)
    assert c._same_domain("https://EXAMPLE.COM/page") is True


def test_other_subdomain_is_still_external():
    c = Crawler(BASE, respect_robots=False)
    assert c._same_domain("https://blog.example.com/page") is False


def test_other_domain_is_still_external():
    c = Crawler(BASE, respect_robots=False)
    assert c._same_domain("https://example.org/page") is False


def test_www_redirect_does_not_strand_the_crawl():
    """The real bug: vagelos.columbia.edu 301s to www.vagelos.columbia.edu, whose
    absolute links were all classified external — crawl ended after one page."""
    site = FakeSite({
        BASE: page(redirect_to=f"{BASE}/home"),
        f"{BASE}/home": page(links=[f"https://www.example.com/a", f"https://www.example.com/b"]),
        "https://www.example.com/a": page(),
        "https://www.example.com/b": page(),
    })
    c = _crawler(site)
    urls = [p.url for p, _, _ in c.crawl()]
    assert "https://www.example.com/a" in urls
    assert "https://www.example.com/b" in urls


def test_start_url_redirecting_cross_host_adopts_the_new_host():
    site = FakeSite({
        BASE: page(redirect_to=OTHER),
        OTHER: page(links=[f"{OTHER}/a"]),
        f"{OTHER}/a": page(),
    })
    c = _crawler(site)
    urls = [p.url for p, _, _ in c.crawl()]
    assert f"{OTHER}/a" in urls, f"crawl stranded on the redirect: {urls}"


def test_a_later_page_redirecting_off_site_does_not_widen_scope():
    site = FakeSite({
        BASE: page(links=["/p1"]),
        f"{BASE}/p1": page(redirect_to=OTHER),
        OTHER: page(links=[f"{OTHER}/a"]),
        f"{OTHER}/a": page(),
    })
    c = _crawler(site)
    urls = [p.url for p, _, _ in c.crawl()]
    assert f"{OTHER}/a" not in urls
    assert sorted(urls) == [BASE, f"{BASE}/p1"]
    assert c.base_netloc == "example.com"


# ── www / non-www must not produce two rows for one page ─────────────────────

def test_www_and_non_www_variants_are_crawled_once():
    site = FakeSite({
        BASE: page(links=["https://www.example.com/", "/a"]),
        "https://www.example.com": page(),
        f"{BASE}/a": page(),
    })
    c = _crawler(site)
    urls = [p.url for p, _, _ in c.crawl()]
    assert len(urls) == 2, f"www variant duplicated the start page: {urls}"
    assert f"{BASE}/a" in urls


def test_reported_url_keeps_the_real_host():
    site = FakeSite({"https://www.example.com": page()})
    c = _crawler(site, start="https://www.example.com")
    urls = [p.url for p, _, _ in c.crawl()]
    assert urls == ["https://www.example.com"]


def test_seed_visited_matches_either_host_form():
    site = FakeSite({BASE: page(links=["/a"]), f"{BASE}/a": page()})
    c = _crawler(site, seed_visited={"https://www.example.com/a"})
    urls = [p.url for p, _, _ in c.crawl()]
    assert f"{BASE}/a" not in urls
