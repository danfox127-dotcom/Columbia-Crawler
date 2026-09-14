from crawler import PageData, ImageInfo, Crawler


def test_page_data_to_dict_structure():
    page = PageData(
        url="https://example.com/test",
        status_code=200,
        title="Test Page",
        h1s=["Test Page"],
        h2s=["Section One"],
        meta_description="A test page",
        canonical="https://example.com/test",
        word_count=100,
        content_snippet="Some content here",
        internal_links=["https://example.com/other"],
        external_links=[],
        is_redirect=False,
        redirect_chain=[],
        images=[ImageInfo(src="https://example.com/img.jpg", alt="An image")],
        load_time=0.123,
        error=None,
    )
    d = page.to_dict()
    assert d["kind"] == "page"
    assert d["url"] == "https://example.com/test"
    assert d["status_code"] == 200
    assert d["title"] == "Test Page"
    assert d["h1s"] == ["Test Page"]
    assert d["h2s"] == ["Section One"]
    assert d["meta_description"] == "A test page"
    assert d["canonical"] == "https://example.com/test"
    assert d["word_count"] == 100
    assert d["content_snippet"] == "Some content here"
    assert d["internal_links"] == ["https://example.com/other"]
    assert d["external_links"] == []
    assert d["is_redirect"] is False
    assert d["redirect_chain"] == []
    assert d["images"] == [{"src": "https://example.com/img.jpg", "alt": "An image"}]
    assert d["load_time"] == 0.123
    assert d["error"] is None


def test_page_data_to_dict_load_time_rounded():
    page = PageData(url="https://example.com", status_code=200, load_time=1.23456789)
    d = page.to_dict()
    assert d["load_time"] == 1.235


def test_page_data_to_dict_image_with_none_alt():
    page = PageData(url="https://example.com", status_code=200)
    page.images = [ImageInfo(src="https://example.com/img.jpg", alt=None)]
    d = page.to_dict()
    assert d["images"] == [{"src": "https://example.com/img.jpg", "alt": None}]


def test_crawler_seed_visited_prepopulated():
    seeded = {"https://example.com/already-crawled"}
    c = Crawler("https://example.com", max_pages=5, respect_robots=False, seed_visited=seeded)
    assert "https://example.com/already-crawled" in c.visited
    assert len(c.visited) == 1


def test_crawler_no_seed_starts_empty():
    c = Crawler("https://example.com", max_pages=5, respect_robots=False)
    assert len(c.visited) == 0


def test_crawler_none_seed_starts_empty():
    c = Crawler("https://example.com", max_pages=5, respect_robots=False, seed_visited=None)
    assert len(c.visited) == 0


def test_crawler_include_paths_allows_matching_url():
    c = Crawler(
        "https://example.com",
        max_pages=5,
        respect_robots=False,
        include_paths=["/faculty/"],
    )
    assert c._is_crawlable("https://example.com/faculty/jane-doe") is True


def test_crawler_include_paths_blocks_non_matching_url():
    c = Crawler(
        "https://example.com",
        max_pages=5,
        respect_robots=False,
        include_paths=["/faculty/"],
    )
    assert c._is_crawlable("https://example.com/news/article") is False


def test_crawler_include_paths_always_allows_start_url():
    c = Crawler(
        "https://example.com",
        max_pages=5,
        respect_robots=False,
        include_paths=["/faculty/"],
    )
    # Start URL itself must pass even though it doesn't match /faculty/
    assert c._is_crawlable("https://example.com") is True


def test_crawler_include_paths_empty_allows_all():
    c = Crawler(
        "https://example.com",
        max_pages=5,
        respect_robots=False,
        include_paths=[],
    )
    assert c._is_crawlable("https://example.com/anything/here") is True


def test_crawler_include_paths_multiple_patterns():
    c = Crawler(
        "https://example.com",
        max_pages=5,
        respect_robots=False,
        include_paths=["/faculty/", "/research/"],
    )
    assert c._is_crawlable("https://example.com/research/cancer") is True
    assert c._is_crawlable("https://example.com/events/2026") is False


def test_crawler_exclude_paths_does_not_match_substring_prefix():
    # "/blog" must not exclude "/blogging-tips" — segment match, not substring
    c = Crawler(
        "https://example.com",
        max_pages=5,
        respect_robots=False,
        exclude_paths=["/blog"],
    )
    assert c._is_crawlable("https://example.com/blog/post-1") is False
    assert c._is_crawlable("https://example.com/blogging-tips/post-1") is True


def test_crawler_include_paths_does_not_match_substring_prefix():
    # "/lab" must not match "/laboratory-safety" — segment match, not substring
    c = Crawler(
        "https://example.com",
        max_pages=5,
        respect_robots=False,
        include_paths=["/lab"],
    )
    assert c._is_crawlable("https://example.com/lab/safety") is True
    assert c._is_crawlable("https://example.com/laboratory-safety") is False


def test_crawler_path_matching_ignores_trailing_slash_either_side():
    c = Crawler(
        "https://example.com",
        max_pages=5,
        respect_robots=False,
        include_paths=["/news/"],
    )
    # Pattern has a trailing slash; folder's own index URL (no trailing slash
    # after normalization) must still match, not just its sub-pages.
    assert c._is_crawlable("https://example.com/news") is True
    assert c._is_crawlable("https://example.com/news/2026/story") is True


def test_crawler_max_depth_limits_subfolder_depth():
    c = Crawler(
        "https://example.com",
        max_pages=5,
        respect_robots=False,
        max_depth=2,
    )
    assert c._is_crawlable("https://example.com/dept/page") is True
    assert c._is_crawlable("https://example.com/dept/sub/page") is False


def test_crawler_max_depth_none_means_unlimited():
    c = Crawler("https://example.com", max_pages=5, respect_robots=False)
    assert c._is_crawlable("https://example.com/a/b/c/d/e") is True


def test_crawler_seed_visited_does_not_mutate_caller():
    seeded = {"https://example.com/already-crawled"}
    c = Crawler("https://example.com", max_pages=5, respect_robots=False, seed_visited=seeded)
    c.visited.add("https://example.com/new-page")
    assert "https://example.com/new-page" not in seeded


# ── relative links must resolve against the post-redirect URL ───────────────

class _FakeResponse:
    """Minimal stand-in for requests.Response as used by Crawler._fetch."""

    def __init__(self, requested_url, final_url, html, history_urls=()):
        self.url = final_url
        self.status_code = 200
        self.headers = {"content-type": "text/html; charset=utf-8"}
        self.text = html
        self.history = [
            type("R", (), {"url": u, "status_code": 301})() for u in history_urls
        ]

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _crawler_with_response(start_url, final_url, html, history_urls=()):
    c = Crawler(start_url, max_pages=5, respect_robots=False, delay=0)
    c.session.get = lambda url, **kw: _FakeResponse(url, final_url, html, history_urls)
    return c


def test_fetch_resolves_relative_links_against_final_redirect_url():
    """A directory URL redirected to its trailing-slash form must not lose the folder."""
    html = '<html><body><a href="research.php">R</a></body></html>'
    c = _crawler_with_response(
        "https://example.com/divisions/kiryluk/",
        "https://example.com/divisions/kiryluk/",
        html,
        history_urls=["https://example.com/divisions/kiryluk"],
    )
    page = c._fetch("https://example.com/divisions/kiryluk")
    assert page.internal_links == ["https://example.com/divisions/kiryluk/research.php"]


def test_fetch_resolves_relative_images_against_final_redirect_url():
    html = '<html><body><img src="img/photo.jpg" alt="p"></body></html>'
    c = _crawler_with_response(
        "https://example.com/divisions/kiryluk/",
        "https://example.com/divisions/kiryluk/",
        html,
        history_urls=["https://example.com/divisions/kiryluk"],
    )
    page = c._fetch("https://example.com/divisions/kiryluk")
    assert page.images[0].src == "https://example.com/divisions/kiryluk/img/photo.jpg"


def test_fetch_uses_requested_url_when_no_redirect():
    html = '<html><body><a href="research.php">R</a></body></html>'
    c = _crawler_with_response(
        "https://example.com/divisions/kiryluk/",
        "https://example.com/divisions/kiryluk/page.php",
        html,
    )
    page = c._fetch("https://example.com/divisions/kiryluk/page.php")
    assert page.internal_links == ["https://example.com/divisions/kiryluk/research.php"]
