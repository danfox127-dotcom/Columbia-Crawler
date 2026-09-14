"""Re-crawls revalidate cached pages instead of skipping or refetching them."""

from crawler import Crawler, PageData
from tests.fake_http import FakeSite, page

BASE = "https://example.com"


def _cached(url, etag=None, last_modified=None, links=(), title="Cached Title"):
    return {
        "kind": "page",
        "url": url,
        "status_code": 200,
        "title": title,
        "h1s": ["Cached H1"],
        "h2s": [],
        "meta_description": "cached meta",
        "canonical": "",
        "word_count": 42,
        "content_snippet": "cached snippet",
        "internal_links": list(links),
        "external_links": [],
        "is_redirect": False,
        "redirect_chain": [],
        "images": [{"src": f"{BASE}/i.png", "alt": "cached alt"}],
        "load_time": 0.1,
        "error": None,
        "etag": etag,
        "last_modified": last_modified,
    }


def _crawler(site, cached_pages=None, **kw):
    kw.setdefault("respect_robots", False)
    kw.setdefault("delay", 0)
    kw.setdefault("max_pages", 100)
    kw.setdefault("max_workers", 1)
    c = Crawler(BASE, cached_pages=cached_pages, **kw)
    c.session.get = site.get
    return c


def test_page_data_to_dict_carries_cache_fields():
    p = PageData(url=BASE, status_code=200, etag='W/"abc"', last_modified="Mon, 01 Jan 2026 00:00:00 GMT")
    d = p.to_dict()
    assert d["etag"] == 'W/"abc"'
    assert d["last_modified"] == "Mon, 01 Jan 2026 00:00:00 GMT"
    assert d["from_cache"] is False


def test_known_url_sends_if_none_match():
    site = FakeSite({BASE: page(etag='"v1"')})
    c = _crawler(site, cached_pages={BASE: _cached(BASE, etag='"v1"')})
    list(c.crawl())
    assert site.headers_for(BASE)[0].get("If-None-Match") == '"v1"'


def test_known_url_sends_if_modified_since():
    stamp = "Mon, 01 Jan 2026 00:00:00 GMT"
    site = FakeSite({BASE: page(last_modified=stamp)})
    c = _crawler(site, cached_pages={BASE: _cached(BASE, last_modified=stamp)})
    list(c.crawl())
    assert site.headers_for(BASE)[0].get("If-Modified-Since") == stamp


def test_unknown_url_sends_no_conditional_headers():
    site = FakeSite({BASE: page()})
    c = _crawler(site)
    list(c.crawl())
    sent = site.headers_for(BASE)[0]
    assert "If-None-Match" not in sent and "If-Modified-Since" not in sent


def test_cached_page_without_validators_is_fetched_unconditionally():
    site = FakeSite({BASE: page()})
    c = _crawler(site, cached_pages={BASE: _cached(BASE)})
    pages = [p for p, _, _ in c.crawl()]
    sent = site.headers_for(BASE)[0]
    assert "If-None-Match" not in sent and "If-Modified-Since" not in sent
    assert pages[0].from_cache is False


def test_304_reuses_stored_record_and_keeps_stored_status():
    site = FakeSite({BASE: page(etag='"v1"')})
    c = _crawler(site, cached_pages={BASE: _cached(BASE, etag='"v1"')})
    p = [pg for pg, _, _ in c.crawl()][0]
    assert p.from_cache is True
    assert p.status_code == 200          # stored status, NOT 304
    assert p.title == "Cached Title"
    assert p.word_count == 42
    assert p.h1s == ["Cached H1"]
    assert p.images[0].alt == "cached alt"
    assert p.error is None


def test_304_reenqueues_stored_links_so_spider_keeps_moving():
    pages = {
        BASE: page(links=["/hub"]),
        f"{BASE}/hub": page(etag='"v1"'),        # unchanged; its html has no links
        f"{BASE}/deep": page(),                  # only reachable via stored links
    }
    site = FakeSite(pages)
    cached = {f"{BASE}/hub": _cached(f"{BASE}/hub", etag='"v1"', links=[f"{BASE}/deep"])}
    c = _crawler(site, cached_pages=cached)
    urls = [p.url for p, _, _ in c.crawl()]
    assert f"{BASE}/deep" in urls


def test_changed_page_is_reparsed_and_new_validators_captured():
    site = FakeSite({BASE: page(etag='"v2"')})
    c = _crawler(site, cached_pages={BASE: _cached(BASE, etag='"v1"')})
    p = [pg for pg, _, _ in c.crawl()][0]
    assert p.from_cache is False
    assert p.title == "t"                # re-parsed from live html
    assert p.etag == '"v2"'


def test_validators_captured_on_a_plain_crawl():
    stamp = "Mon, 01 Jan 2026 00:00:00 GMT"
    site = FakeSite({BASE: page(etag='"v9"', last_modified=stamp)})
    c = _crawler(site)
    p = [pg for pg, _, _ in c.crawl()][0]
    assert p.etag == '"v9"'
    assert p.last_modified == stamp


def test_validators_without_a_usable_record_trigger_an_unconditional_refetch():
    """Caller supplied an ETag but no real stored page — revalidating would
    otherwise reuse a blank record and report status 0."""
    site = FakeSite({BASE: page(etag='"v1"')})
    c = _crawler(site, cached_pages={BASE: {"etag": '"v1"'}})
    p = [pg for pg, _, _ in c.crawl()][0]
    sent = site.headers_for(BASE)
    assert len(sent) == 2
    assert sent[0].get("If-None-Match") == '"v1"'
    assert "If-None-Match" not in sent[1]
    assert p.from_cache is False
    assert p.title == "t"
    assert p.status_code == 200


def test_unconditional_304_is_reported_as_is_without_refetching():
    """A server that 304s a request carrying no validators is misbehaving;
    report it rather than re-asking the identical question forever."""
    site = FakeSite({BASE: page(always_304=True)})
    c = _crawler(site)
    pages = [pg for pg, _, _ in c.crawl()]
    assert len(site.headers_for(BASE)) == 1
    assert len(pages) == 1
    assert pages[0].status_code == 304


def test_cached_keys_match_regardless_of_trailing_slash():
    site = FakeSite({BASE: page(etag='"v1"')})
    c = _crawler(site, cached_pages={f"{BASE}/": _cached(BASE, etag='"v1"')})
    p = [pg for pg, _, _ in c.crawl()][0]
    assert p.from_cache is True
