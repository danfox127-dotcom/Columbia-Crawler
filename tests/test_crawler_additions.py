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
