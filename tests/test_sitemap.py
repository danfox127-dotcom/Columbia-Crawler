"""Sitemap scanning: path filters and failures that must not look like 'no URLs'."""

import requests

from crawler import CHALLENGE_ERROR
from sitemap import check_url, fetch_sitemap_urls

SITEMAP = "https://example.com/sitemap.xml"


class _Resp:
    def __init__(self, status=200, body="", headers=None):
        self.status_code = status
        self.text = body
        self.content = body.encode("utf-8")
        self.headers = headers or {"content-type": "application/xml"}


def _urlset(*paths):
    locs = "".join(f"<url><loc>https://example.com{p}</loc></url>" for p in paths)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</urlset>'
    )


def _index(*sitemaps):
    locs = "".join(f"<sitemap><loc>{s}</loc></sitemap>" for s in sitemaps)
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        f'<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">{locs}</sitemapindex>'
    )


def _get(routes):
    def get(url, **kwargs):
        resp = routes.get(url)
        if isinstance(resp, Exception):
            raise resp
        return resp or _Resp(404, "Not found", {"content-type": "text/html"})
    return get


_CHALLENGE = {"content-type": "text/html", "cf-mitigated": "challenge"}


# ── path filters ────────────────────────────────────────────────────────────

def test_include_paths_keep_only_matching_folders():
    routes = {SITEMAP: _Resp(body=_urlset("/", "/team", "/team/alice", "/teamwork", "/news/x"))}
    res = fetch_sitemap_urls(SITEMAP, 100, included_paths=["/team/"], get=_get(routes))

    assert res.urls == ["https://example.com/team", "https://example.com/team/alice"]
    assert res.warnings == []


def test_exclude_paths_match_nested_folders():
    routes = {SITEMAP: _Resp(body=_urlset("/a/b/one", "/a/c/two", "/b/three"))}
    res = fetch_sitemap_urls(SITEMAP, 100, excluded_paths=["/a/b/"], get=_get(routes))

    assert res.urls == ["https://example.com/a/c/two", "https://example.com/b/three"]


def test_include_path_matching_nothing_warns():
    routes = {SITEMAP: _Resp(body=_urlset("/kidney-bladder", "/kidney-bladder/about"))}
    res = fetch_sitemap_urls(
        SITEMAP, 100, included_paths=["/kidney-bladder/", "/kidney-and-bladder/"], get=_get(routes)
    )

    assert len(res.urls) == 2
    assert len(res.warnings) == 1
    assert "/kidney-and-bladder/" in res.warnings[0]


def test_unmatched_include_is_not_blamed_when_max_urls_cut_the_scan_short():
    routes = {SITEMAP: _Resp(body=_urlset("/a/1", "/a/2", "/b/1"))}
    res = fetch_sitemap_urls(SITEMAP, 2, included_paths=["/a/", "/b/"], get=_get(routes))

    assert res.urls == ["https://example.com/a/1", "https://example.com/a/2"]
    assert res.warnings == []


# ── failures surface as warnings ────────────────────────────────────────────

def test_challenged_sitemap_warns_about_cloudflare():
    res = fetch_sitemap_urls(SITEMAP, 100, get=_get({SITEMAP: _Resp(403, "<html>", _CHALLENGE)}))

    assert res.urls == []
    assert len(res.warnings) == 1
    assert "Cloudflare" in res.warnings[0]


def test_http_error_on_sitemap_reports_status():
    res = fetch_sitemap_urls(SITEMAP, 100, get=_get({}))

    assert res.urls == []
    assert "404" in res.warnings[0]


def test_unreachable_sitemap_warns():
    routes = {SITEMAP: requests.ConnectionError("boom")}
    res = fetch_sitemap_urls(SITEMAP, 100, get=_get(routes))

    assert res.urls == []
    assert "ConnectionError" in res.warnings[0]


def test_non_xml_sitemap_warns():
    routes = {SITEMAP: _Resp(body="<html><body>Not a sitemap</body></html>")}
    res = fetch_sitemap_urls(SITEMAP, 100, get=_get(routes))

    assert res.urls == []
    assert "XML" in res.warnings[0]


def test_failed_child_sitemap_warns_but_keeps_the_rest():
    a = "https://example.com/a.xml"
    b = "https://example.com/b.xml"
    routes = {
        SITEMAP: _Resp(body=_index(a, b)),
        a: _Resp(body=_urlset("/one")),
        b: _Resp(403, "<html>", _CHALLENGE),
    }
    res = fetch_sitemap_urls(SITEMAP, 100, get=_get(routes))

    assert res.urls == ["https://example.com/one"]
    assert len(res.warnings) == 1
    assert b in res.warnings[0]


# ── page checks ─────────────────────────────────────────────────────────────

class _Session:
    def __init__(self, resp):
        self.resp = resp

    def get(self, url, **kwargs):
        return self.resp


def test_check_url_flags_challenged_page():
    row = check_url("https://example.com/x", _Session(_Resp(403, "<html>", _CHALLENGE)))

    assert row["status"] == 403
    assert row["error"] == CHALLENGE_ERROR


def test_check_url_parses_normal_page():
    html = "<html><head><title>T</title></head><body><h1>H</h1>one two</body></html>"
    row = check_url("https://example.com/x", _Session(_Resp(200, html, {"content-type": "text/html"})))

    assert (row["status"], row["title"], row["h1"], row["error"]) == (200, "T", "H", None)
