"""Include paths seed the crawl and flag folders that never load."""

from crawler import Crawler
from tests.fake_http import FakeSite, page

BASE = "https://example.com"


def _crawler(site, **kw):
    kw.setdefault("respect_robots", False)
    kw.setdefault("delay", 0)
    c = Crawler(BASE, **kw)
    c.session.get = site.get
    return c


def test_include_folder_is_crawled_even_when_start_page_does_not_link_to_it():
    site = FakeSite({
        BASE: page(links=["/elsewhere"]),
        f"{BASE}/team": page(links=["/team/alice", "/team/bob"]),
        f"{BASE}/team/alice": page(),
        f"{BASE}/team/bob": page(),
    })
    c = _crawler(site, include_paths=["/team/"])

    urls = sorted(p.url for p, _, _ in c.crawl())

    assert urls == [BASE, f"{BASE}/team", f"{BASE}/team/alice", f"{BASE}/team/bob"]
    assert c.warnings == []


def test_include_path_without_leading_slash_is_seeded():
    site = FakeSite({BASE: page(), f"{BASE}/team": page()})
    c = _crawler(site, include_paths=["team"])

    assert f"{BASE}/team" in [p.url for p, _, _ in c.crawl()]


def test_misspelled_include_folder_shows_up_and_warns():
    site = FakeSite({
        BASE: page(links=["/kidney-bladder"]),
        f"{BASE}/kidney-bladder": page(),
    })
    c = _crawler(site, include_paths=["/kidney-and-bladder/"])

    pages = {p.url: p.status_code for p, _, _ in c.crawl()}

    assert pages[f"{BASE}/kidney-and-bladder"] == 404
    assert len(c.warnings) == 1
    assert "/kidney-and-bladder/" in c.warnings[0]


def test_only_the_folder_that_failed_is_warned_about():
    site = FakeSite({BASE: page(), f"{BASE}/good": page()})
    c = _crawler(site, include_paths=["/good/", "/bad/"])
    list(c.crawl())

    assert len(c.warnings) == 1
    assert "/bad/" in c.warnings[0]


def test_seed_still_respects_exclude_paths():
    site = FakeSite({BASE: page(), f"{BASE}/team": page()})
    c = _crawler(site, include_paths=["/team/"], exclude_paths=["/team/"])

    assert [p.url for p, _, _ in c.crawl()] == [BASE]


def test_children_only_exclude_skips_subpages_but_keeps_landing_page():
    """'/library/*' skips the library's articles but still visits /library itself."""
    site = FakeSite({
        BASE: page(links=["/library", "/about"]),
        f"{BASE}/library": page(links=["/library/a", "/library/b"]),
        f"{BASE}/library/a": page(),
        f"{BASE}/library/b": page(),
        f"{BASE}/about": page(),
    })
    c = _crawler(site, exclude_paths=["/library/*"])
    assert sorted(p.url for p, _, _ in c.crawl()) == [BASE, f"{BASE}/about", f"{BASE}/library"]


def test_children_only_suffix_on_an_include_means_the_whole_folder():
    """An include needs the folder page to discover its subpages, so 'team/*' == 'team'."""
    site = FakeSite({
        BASE: page(),
        f"{BASE}/team": page(links=["/team/alice"]),
        f"{BASE}/team/alice": page(),
    })
    c = _crawler(site, include_paths=["team/*"])
    urls = sorted(p.url for p, _, _ in c.crawl())
    assert urls == [BASE, f"{BASE}/team", f"{BASE}/team/alice"]
    assert c.warnings == []


def test_path_patterns():
    m = Crawler._path_matches
    assert m("/library/*", "/library/article/x") and m("library/*", "/library/a")
    assert not m("/library/*", "/library") and not m("/library/*", "/library/")
    assert not m("/library/*", "/library-news/x")
    assert m("/library", "/library") and m("/library", "/library/a")
    assert not m("/*", "/anything") and not m("", "/x")
    assert m("/Library/*", "/library/A")


def test_add_seeds_reaches_orphan_pages():
    site = FakeSite({
        BASE: page(links=["/a"]),
        f"{BASE}/a": page(),
        f"{BASE}/orphan": page(links=["/orphan/child"]),
        f"{BASE}/orphan/child": page(),
        f"{BASE}/skipped/x": page(),
    })
    c = _crawler(site, exclude_paths=["/skipped"])
    queued = c.add_seeds([f"{BASE}/orphan", f"{BASE}/a", "https://other.example/page",
                          f"{BASE}/skipped/x", "mailto:x@example.com", ""])
    assert queued == 2  # orphan + a (a is deduped when claimed)
    urls = sorted(p.url for p, _, _ in c.crawl())
    assert urls == [BASE, f"{BASE}/a", f"{BASE}/orphan", f"{BASE}/orphan/child"]


def test_sitemap_urls_without_robots_is_empty():
    assert _crawler(FakeSite({BASE: page()})).sitemap_urls() == []
