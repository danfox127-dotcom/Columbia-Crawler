import json
import pytest
from schemas.linkup_export_v1 import (
    build_header,
    build_export_jsonl,
    parse_export_jsonl,
    SCHEMA_VERSION,
    SOURCE_APP,
    SOURCE_APP_VERSION,
)


def test_build_header_required_fields():
    h = build_header("https://example.com", "bfs", 100, 10, [], [])
    assert h["kind"] == "header"
    assert h["schema_version"] == SCHEMA_VERSION
    assert h["source_app"] == SOURCE_APP
    assert h["start_url"] == "https://example.com"
    assert h["crawl_mode"] == "bfs"
    assert h["max_pages"] == 100
    assert h["pages_crawled"] == 10
    assert "generated_at" in h
    assert h["source_app_version"] == SOURCE_APP_VERSION


def test_build_header_exclude_paths():
    h = build_header("https://example.com", "sitemap", 500, 400, ["/news/", "/events/"], [])
    assert h["exclude_paths"] == ["/news/", "/events/"]
    assert h["include_paths"] == []


def test_build_header_generated_at_format():
    import re
    h = build_header("https://example.com", "bfs", 10, 5, [], [])
    assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$', h["generated_at"])


def _make_page(url, status=200):
    return {
        "kind": "page",
        "url": url,
        "status_code": status,
        "title": "Test",
        "h1s": ["Test"],
        "h2s": [],
        "meta_description": "",
        "canonical": url,
        "word_count": 50,
        "content_snippet": "some content",
        "internal_links": [],
        "external_links": [],
        "is_redirect": False,
        "redirect_chain": [],
        "images": [],
        "load_time": 0.1,
        "error": None,
    }


def test_round_trip():
    header = build_header("https://example.com", "bfs", 100, 2, [], [])
    pages = [_make_page("https://example.com/a"), _make_page("https://example.com/b", 404)]
    jsonl = build_export_jsonl(header, pages)
    parsed_header, parsed_pages = parse_export_jsonl(jsonl)
    assert parsed_header["start_url"] == "https://example.com"
    assert len(parsed_pages) == 2
    assert parsed_pages[0]["url"] == "https://example.com/a"
    assert parsed_pages[1]["status_code"] == 404


def test_round_trip_all_lines_valid_json():
    header = build_header("https://example.com", "bfs", 10, 1, [], [])
    pages = [_make_page("https://example.com/x")]
    jsonl = build_export_jsonl(header, pages)
    for line in jsonl.splitlines():
        json.loads(line)  # must not raise


def test_parse_ignores_invalid_json_lines():
    content = (
        '{"kind":"header","schema_version":"linkup_export.v1","source_app":"content_ct",'
        '"start_url":"https://x.com","generated_at":"2026-01-01T00:00:00Z",'
        '"crawl_mode":"bfs","max_pages":10,"pages_crawled":1,"exclude_paths":[],"include_paths":[]}\n'
        'not valid json\n'
        '{"kind":"page","url":"https://x.com/a","status_code":200}'
    )
    header, pages = parse_export_jsonl(content)
    assert header is not None
    assert len(pages) == 1


def test_parse_empty_string():
    header, pages = parse_export_jsonl("")
    assert header is None
    assert pages == []


def test_parse_no_header():
    content = '{"kind":"page","url":"https://x.com/a","status_code":200}\n'
    header, pages = parse_export_jsonl(content)
    assert header is None
    assert len(pages) == 1


def test_parse_duplicate_header_raises():
    content = (
        '{"kind":"header","schema_version":"linkup_export.v1","source_app":"content_ct","start_url":"https://x.com","generated_at":"2026-01-01T00:00:00Z","crawl_mode":"bfs","max_pages":10,"pages_crawled":1,"exclude_paths":[],"include_paths":[]}\n'
        '{"kind":"header","schema_version":"linkup_export.v1","source_app":"content_ct","start_url":"https://y.com","generated_at":"2026-01-01T00:00:00Z","crawl_mode":"bfs","max_pages":10,"pages_crawled":1,"exclude_paths":[],"include_paths":[]}\n'
    )
    with pytest.raises(ValueError, match="duplicate header"):
        parse_export_jsonl(content)
