"""
sitemap.py — sitemap URL discovery and per-URL SEO checks for Sitemap mode.
"""

import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from typing import Callable, List, Optional
from urllib.parse import urlparse

import requests  # type: ignore
from bs4 import BeautifulSoup  # type: ignore

from crawler import CHALLENGE_ERROR, Crawler, _is_bot_challenge

_path_matches = Crawler._path_matches


@dataclass
class SitemapResult:
    urls: List[str] = field(default_factory=list)
    # Sitemaps that couldn't be read, include paths that matched nothing, etc.
    warnings: List[str] = field(default_factory=list)


def fetch_sitemap_urls(
    sitemap_url: str,
    max_urls: int,
    excluded_paths: Optional[List[str]] = None,
    included_paths: Optional[List[str]] = None,
    get: Callable = requests.get,
    auth: Optional[requests.auth.AuthBase] = None,
) -> SitemapResult:
    """Recursively collect <loc> URLs from a sitemap or sitemap index.

    Path filters match by folder segment at any depth, the same as crawl mode.
    """
    excluded = [p for p in (excluded_paths or []) if p.strip().strip("/")]
    included = [p for p in (included_paths or []) if p.strip().strip("/")]
    result = SitemapResult()
    seen_sitemaps = set()
    matched_includes = set()

    def _fetch(url, depth=0):
        if depth > 4 or url in seen_sitemaps or len(result.urls) >= max_urls:
            return
        seen_sitemaps.add(url)
        try:
            resp = get(url, timeout=15, headers={"User-Agent": "Mozilla/5.0"}, auth=auth)
        except requests.RequestException as exc:
            result.warnings.append(f"Could not fetch sitemap {url} ({type(exc).__name__}).")
            return
        if _is_bot_challenge(resp):
            result.warnings.append(f"Sitemap {url} is behind a Cloudflare bot challenge.")
            return
        if resp.status_code >= 400:
            result.warnings.append(f"Sitemap {url} returned {resp.status_code}.")
            return
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            result.warnings.append(f"Sitemap {url} is not valid XML.")
            return

        ns = root.tag.split("}")[0].lstrip("{") if "}" in root.tag else ""
        pre = f"{{{ns}}}" if ns else ""
        tag = root.tag.split("}")[-1]
        if tag not in ("sitemapindex", "urlset"):
            result.warnings.append(f"Sitemap {url} is not sitemap XML (got <{tag}>).")
            return

        if tag == "sitemapindex":
            for sm in root.findall(f"{pre}sitemap"):
                loc = sm.find(f"{pre}loc")
                if loc is not None and loc.text:
                    _fetch(loc.text.strip(), depth + 1)
                    if len(result.urls) >= max_urls:
                        return
        else:
            for url_el in root.findall(f"{pre}url"):
                loc = url_el.find(f"{pre}loc")
                if loc is None or not loc.text:
                    continue
                page_url = loc.text.strip()
                path = urlparse(page_url).path.lower()
                if any(_path_matches(ex, path) for ex in excluded):
                    continue
                if included:
                    hits = [inc for inc in included if _path_matches(inc, path)]
                    if not hits:
                        continue
                    matched_includes.update(hits)
                result.urls.append(page_url)
                if len(result.urls) >= max_urls:
                    return

    _fetch(sitemap_url)

    # A cut-short scan can't tell a misspelled folder from one it never reached.
    if len(result.urls) < max_urls:
        for inc in included:
            if inc not in matched_includes:
                result.warnings.append(
                    f"No sitemap URLs fall under include path {inc}. "
                    "Check the folder name is spelled as it appears in the site's URLs."
                )
    return result


def check_url(url: str, session) -> dict:
    """Fetch one page and pull the basic SEO fields. `error` is set for pages
    that were blocked or failed outright."""
    row = {"url": url, "status": 0, "title": "", "h1": "", "meta_desc": "", "word_count": 0,
           "error": None}
    try:
        resp = session.get(url, timeout=10)
        row["status"] = resp.status_code
        if _is_bot_challenge(resp):
            row["error"] = CHALLENGE_ERROR
            return row
        if resp.status_code != 200 or not resp.text:
            return row
        soup = BeautifulSoup(resp.text, "html.parser")
        row["title"] = soup.title.string.strip() if soup.title and soup.title.string else ""
        h1_tag = soup.find("h1")
        row["h1"] = h1_tag.get_text(strip=True) if h1_tag else ""
        meta_tag = soup.find("meta", attrs={"name": "description"})
        row["meta_desc"] = (meta_tag.get("content") or "").strip() if meta_tag else ""
        body = soup.find("body")
        row["word_count"] = len(body.get_text(separator=" ", strip=True).split()) if body else 0
    except Exception as exc:
        row["error"] = str(exc)[:80]
    return row
