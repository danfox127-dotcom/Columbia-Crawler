"""
crawler.py — lightweight BFS web crawler using requests + BeautifulSoup.
Replaces the subprocess/Scrapy approach from Columbia-Crawler.
"""

import re
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Generator, List, Optional, Tuple
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

import requests  # type: ignore
from bs4 import BeautifulSoup  # type: ignore
from requests.adapters import HTTPAdapter  # type: ignore
from urllib3.util.retry import Retry  # type: ignore


@dataclass
class ImageInfo:
    src: str
    alt: Optional[str]  # None = attribute absent; '' = explicitly empty


@dataclass
class PageData:
    url: str
    status_code: int = 0
    title: str = ""
    h1s: List[str] = field(default_factory=list)
    h2s: List[str] = field(default_factory=list)
    meta_description: str = ""
    canonical: str = ""
    word_count: int = 0
    load_time: float = 0.0
    images: List[ImageInfo] = field(default_factory=list)
    internal_links: List[str] = field(default_factory=list)
    external_links: List[str] = field(default_factory=list)
    is_redirect: bool = False
    redirect_chain: List[str] = field(default_factory=list)
    content_snippet: str = ""
    error: Optional[str] = None


class Crawler:
    _HEADERS = {
        "User-Agent": (
            "ContentCT/1.0 SEO Audit Tool "
            "(github.com/danfox127-dotcom/Columbia-Crawler)"
        )
    }

    _EXCLUDED_EXTENSIONS = {
        ".css", ".js", ".json", ".xml", ".pdf", ".zip", ".rar", ".gz", ".tar",
        ".mp3", ".mp4", ".avi", ".mov", ".jpg", ".jpeg", ".png", ".gif", ".svg",
        ".webp", ".ico", ".ttf", ".woff", ".woff2", ".eot", ".csv", ".xls",
        ".xlsx", ".doc", ".docx", ".ppt", ".pptx", ".txt"
    }

    def __init__(
        self,
        start_url: str,
        max_pages: int = 100,
        delay: float = 0.5,
        respect_robots: bool = True,
        timeout: int = 10,
        exclude_paths: Optional[List[str]] = None,
        include_paths: Optional[List[str]] = None,
    ):
        self.start_url = start_url.rstrip("/")
        self.max_pages = max_pages
        self.delay = delay
        self.timeout = timeout
        self.exclude_paths = exclude_paths or []
        self.include_paths = include_paths or []

        parsed = urlparse(start_url)
        self.base_netloc = parsed.netloc

        self.visited: "set[str]" = set()
        self.queue: "deque[str]" = deque([self.start_url])

        self.session = requests.Session()
        self.session.headers.update(self._HEADERS)
        
        # Robustness: Auto-retry on transient errors or rate limits
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(max_retries=retries)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)

        self.robots: Optional[RobotFileParser] = None
        if respect_robots:
            self._load_robots(start_url)

    # ── robots.txt ──────────────────────────────────────────────────────────

    def _load_robots(self, start_url: str) -> None:
        parsed = urlparse(start_url)
        robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
        rp = RobotFileParser(robots_url)
        try:
            rp.read()
            self.robots = rp
        except Exception:
            pass

    def _can_fetch(self, url: str) -> bool:
        robots = self.robots
        if robots is None:
            return True
        return robots.can_fetch("*", url)

    # ── URL helpers ─────────────────────────────────────────────────────────

    def _same_domain(self, url: str) -> bool:
        return urlparse(url).netloc == self.base_netloc

    def _is_crawlable(self, url: str) -> bool:
        path = urlparse(url).path.lower()
        if any(path.endswith(ext) for ext in self._EXCLUDED_EXTENSIONS):
            return False
            
        for ex in self.exclude_paths:
            if ex.lower() in path:
                return False
                
        if self.include_paths:
            # Always allow the start URL so we can spider from it
            if self._normalize(url) != self._normalize(self.start_url):
                if not any(inc.lower() in path for inc in self.include_paths):
                    return False
                    
        return True

    @staticmethod
    def _normalize(url: str) -> str:
        p = urlparse(url)
        return p._replace(fragment="").geturl().rstrip("/")

    # ── Public crawl interface ───────────────────────────────────────────────

    def crawl(self) -> Generator[Tuple[PageData, int, int], None, None]:
        """
        Yield (PageData, pages_done, queue_remaining) as the crawl progresses.
        Callers can use pages_done / (pages_done + queue_remaining) for progress.
        """
        while self.queue and len(self.visited) < self.max_pages:
            url = self._normalize(self.queue.popleft())

            if url in self.visited or not self._can_fetch(url):
                continue

            self.visited.add(url)
            page = self._fetch(url)

            for link in page.internal_links:
                norm = self._normalize(link)
                if norm not in self.visited and self._is_crawlable(norm):
                    self.queue.append(norm)

            yield page, len(self.visited), len(self.queue)

            if self.delay > 0:
                time.sleep(self.delay)

    # ── Fetch & parse ────────────────────────────────────────────────────────

    def _fetch(self, url: str) -> PageData:
        page = PageData(url=url)
        t0 = time.time()
        try:
            with self.session.get(url, timeout=self.timeout, allow_redirects=True, stream=True) as resp:
                page.load_time = time.time() - t0
                page.status_code = resp.status_code

                if resp.history:
                    page.is_redirect = True
                    page.redirect_chain = [r.url for r in resp.history] + [resp.url]

                if "text/html" not in resp.headers.get("content-type", "").lower():
                    return page

                html = resp.text

            self._parse(page, html, url)

        except requests.Timeout:
            page.load_time = time.time() - t0
            page.status_code = 0
            page.error = "Timeout"
        except requests.ConnectionError as exc:
            page.load_time = time.time() - t0
            page.status_code = 0
            page.error = f"Connection error: {str(exc)[:60]}"  # type: ignore
        except Exception as exc:
            page.load_time = time.time() - t0
            page.status_code = 0
            page.error = str(exc)[:80]  # type: ignore

        return page

    def _parse(self, page: PageData, html: str, base_url: str) -> None:
        try:
            soup = BeautifulSoup(html, "lxml")
        except Exception:
            soup = BeautifulSoup(html, "html.parser")

        # Title
        title_tag = soup.find("title")
        page.title = title_tag.get_text(strip=True) if title_tag else ""

        # H1s
        page.h1s = [
            h.get_text(strip=True)
            for h in soup.find_all("h1")
            if h.get_text(strip=True)
        ]

        # H2s
        page.h2s = [
            h.get_text(strip=True)
            for h in soup.find_all("h2")
            if h.get_text(strip=True)
        ]

        # Meta description
        meta = soup.find("meta", attrs={"name": re.compile(r"^description$", re.I)})
        if meta:
            content = meta.get("content", "")
            page.meta_description = (content[0] if isinstance(content, list) else content).strip()

        # Canonical
        canonical = soup.find("link", attrs={"rel": re.compile(r"canonical", re.I)})
        if canonical:
            c_href = canonical.get("href", "")
            page.canonical = (c_href[0] if isinstance(c_href, list) else c_href).strip()

        # Word count — strip boilerplate first
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        body = soup.find("body")
        if body:
            text = body.get_text(separator=" ", strip=True)
            words = text.split()
            page.word_count = len(words)
            page.content_snippet = " ".join(words[:120])  # ~600 chars for AI prompts

        # Images
        for img in soup.find_all("img"):
            src_val = img.get("src", "")
            src = (src_val[0] if isinstance(src_val, list) else src_val).strip()
            if not src or src.startswith("data:"):
                continue
            abs_src = urljoin(base_url, src)
            alt_val = img.get("alt", None)
            alt = alt_val[0] if isinstance(alt_val, list) else alt_val # type: ignore
            page.images.append(ImageInfo(src=abs_src, alt=alt))

        # Links
        for a in soup.find_all("a", href=True):
            href_val = a["href"]
            href = (href_val[0] if isinstance(href_val, list) else href_val).strip()
            if not href or href.startswith(("#", "mailto:", "tel:", "javascript:")):
                continue
            abs_href = urljoin(base_url, href)
            p = urlparse(abs_href)
            if p.scheme not in ("http", "https"):
                continue
            if self._same_domain(abs_href):
                page.internal_links.append(abs_href)
            else:
                page.external_links.append(abs_href)
