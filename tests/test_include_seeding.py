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
