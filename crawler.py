"""
crawler.py — lightweight BFS web crawler using requests + BeautifulSoup.
Replaces the subprocess/Scrapy approach from Columbia-Crawler.
"""

import re
import threading
import time
from collections import deque
from concurrent.futures import FIRST_COMPLETED, ThreadPoolExecutor, wait
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
    etag: str = ""
    last_modified: str = ""
    from_cache: bool = False

    def to_dict(self) -> dict:
        return {
            "kind": "page",
            "url": self.url,
            "status_code": self.status_code,
            "title": self.title,
            "h1s": list(self.h1s),
            "h2s": list(self.h2s),
            "meta_description": self.meta_description,
            "canonical": self.canonical,
            "word_count": self.word_count,
            "content_snippet": self.content_snippet,
            "internal_links": list(self.internal_links),
            "external_links": list(self.external_links),
            "is_redirect": self.is_redirect,
            "redirect_chain": list(self.redirect_chain),
            "images": [{"src": img.src, "alt": img.alt} for img in self.images],
            "load_time": round(self.load_time, 3),
            "error": self.error,
            "etag": self.etag,
            "last_modified": self.last_modified,
            "from_cache": self.from_cache,
        }


class _RateLimiter:
    """Per-host politeness gate shared by every worker thread.

    Holds a minimum interval between request starts, widens it when the host
    pushes back with 429/503, and decays back toward the baseline once the host
    is answering normally again.
    """

    _BACKOFF_CAP = 2.0
    _BACKOFF_FLOOR = 0.25
    _DECAY_AFTER = 5

    def __init__(self, min_interval: float = 0.0):
        self.baseline = max(0.0, float(min_interval))
        self.interval = self.baseline
        self._next_at = 0.0
        self._successes = 0
        self._lock = threading.Lock()

    def acquire(self) -> None:
        """Block until this thread's turn, then reserve the next slot."""
        with self._lock:
            now = time.monotonic()
            wait_for = max(0.0, self._next_at - now)
            self._next_at = max(now, self._next_at) + self.interval
        if wait_for > 0:
            time.sleep(wait_for)

    def on_response(self, status: int) -> None:
        with self._lock:
            if status in (429, 503):
                self._successes = 0
                # Double what we were doing; the floor only kicks in when there
                # is nothing to double (an unthrottled crawl at interval 0).
                widened = self.interval * 2 if self.interval > 0 else self._BACKOFF_FLOOR
                self.interval = min(widened, self._BACKOFF_CAP)
            elif 200 <= status < 400:
                self._successes += 1
                if self._successes >= self._DECAY_AFTER and self.interval > self.baseline:
                    self.interval = max(self.baseline, self.interval / 2)
                    self._successes = 0


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
        max_depth: Optional[int] = None,
        seed_visited: Optional[set] = None,
        max_workers: int = 8,
        cached_pages: Optional[dict] = None,
    ):
        self.start_url = start_url.rstrip("/")
        self.max_pages = max_pages
        self.delay = delay
        self.timeout = timeout
        self.exclude_paths = exclude_paths or []
        self.include_paths = include_paths or []
        self.max_depth = max_depth
        self.max_workers = max(1, int(max_workers))
        self.limiter = _RateLimiter(delay)
        # url -> previously exported page dict, used to revalidate instead of
        # refetching. Keys are normalized so a stored "/a/" matches a crawled "/a".
        self.cached_pages: dict = {
            self._normalize(k): v for k, v in (cached_pages or {}).items() if k
        }

        parsed = urlparse(start_url)
        self.base_netloc = parsed.netloc

        self.visited: "set[str]" = set(seed_visited) if seed_visited is not None else set()
        self.queue: "deque[str]" = deque([self.start_url])

        # Guards visited / queue / the counters below, all of which are touched
        # by the driver thread while workers are in flight.
        self.lock = threading.Lock()
        self.claimed = 0      # URLs handed to a worker; caps at max_pages
        self.completed = 0    # pages yielded to the caller

        self.session = requests.Session()
        self.session.headers.update(self._HEADERS)
        
        # Robustness: Auto-retry on transient errors or rate limits
        retries = Retry(
            total=3,
            backoff_factor=0.5,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"]
        )
        adapter = HTTPAdapter(
            max_retries=retries,
            pool_connections=max(self.max_workers, 10),
            pool_maxsize=max(self.max_workers, 10),
        )
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
            self._apply_robots_delay(rp)
        except Exception:
            pass

    def _apply_robots_delay(self, robots) -> None:
        """Raise the minimum interval to robots.txt Crawl-delay when it asks for
        more than we were already giving. Never lowers a configured delay."""
        try:
            declared = robots.crawl_delay("*")
        except Exception:
            return
        if declared and float(declared) > self.limiter.baseline:
            self.limiter.baseline = float(declared)
            self.limiter.interval = float(declared)

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

        if self.max_depth is not None and self._path_depth(path) > self.max_depth:
            return False

        for ex in self.exclude_paths:
            if self._path_matches(ex, path):
                return False

        if self.include_paths:
            # Always allow the start URL so we can spider from it
            if self._normalize(url) != self._normalize(self.start_url):
                if not any(self._path_matches(inc, path) for inc in self.include_paths):
                    return False

        return True

    @staticmethod
    def _path_matches(pattern: str, path: str) -> bool:
        """True if `path` is the folder identified by `pattern` or lives under it.

        Matches by path segment, not raw substring, and is agnostic to trailing
        slashes on either side (e.g. pattern "/blog/" matches "/blog" and
        "/blog/post-1", but not "/blogging-tips").
        """
        pattern = pattern.strip().lower()
        if not pattern:
            return False
        if not pattern.startswith("/"):
            pattern = "/" + pattern
        pattern = pattern.rstrip("/")
        path = path.rstrip("/")
        return path == pattern or path.startswith(pattern + "/")

    @staticmethod
    def _path_depth(path: str) -> int:
        """Number of non-empty folder segments in a URL path, e.g. /a/b/c -> 3."""
        return len([seg for seg in path.strip("/").split("/") if seg])

    @staticmethod
    def _normalize(url: str) -> str:
        p = urlparse(url)
        return p._replace(fragment="").geturl().rstrip("/")

    # ── Public crawl interface ───────────────────────────────────────────────

    def crawl(self) -> Generator[Tuple[PageData, int, int], None, None]:
        """
        Yield (PageData, pages_done, queue_remaining) as the crawl progresses.
        Callers can use pages_done / (pages_done + queue_remaining) for progress.

        Fetching runs on a rolling window of `max_workers` threads: as each
        request finishes, its links are enqueued and the next URL starts, so one
        slow page never stalls the other workers. Yields happen on the calling
        thread, which keeps Streamlit widget updates off the worker threads.
        """
        in_flight: "dict" = {}
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            while True:
                while len(in_flight) < self.max_workers:
                    url = self._claim_next()
                    if url is None:
                        break
                    in_flight[executor.submit(self._fetch_guarded, url)] = url

                if not in_flight:
                    break

                done, _ = wait(list(in_flight.keys()), return_when=FIRST_COMPLETED)
                for future in done:
                    url = in_flight.pop(future)
                    page = future.result()
                    self._enqueue_links(page)
                    with self.lock:
                        self.completed += 1
                        done_count = self.completed
                        remaining = len(self.queue) + len(in_flight)
                    yield page, done_count, remaining

    def _claim_next(self) -> Optional[str]:
        """Pop the next crawlable URL and mark it taken, or None if exhausted.

        Claiming (rather than counting on yield) is what keeps a partial window
        from over-fetching past max_pages.
        """
        with self.lock:
            while self.queue:
                if self.claimed >= self.max_pages:
                    return None
                url = self._normalize(self.queue.popleft())
                if url in self.visited or not self._can_fetch(url):
                    continue
                self.visited.add(url)
                self.claimed += 1
                return url
        return None

    def _enqueue_links(self, page: PageData) -> None:
        with self.lock:
            for link in page.internal_links:
                norm = self._normalize(link)
                if norm not in self.visited and self._is_crawlable(norm):
                    self.queue.append(norm)

    def _fetch_guarded(self, url: str) -> PageData:
        """_fetch already converts request failures into an errored PageData;
        this catches anything else so one bad worker cannot kill the crawl."""
        try:
            return self._fetch(url)
        except Exception as exc:
            return PageData(url=url, status_code=0, error=str(exc)[:80])

    # ── Fetch & parse ────────────────────────────────────────────────────────

    @staticmethod
    def _page_from_cache(cached: dict, url: str, load_time: float) -> PageData:
        """Rebuild PageData from a previously exported page dict (304 hit)."""
        return PageData(
            url=url,
            status_code=int(cached.get("status_code") or 0),
            title=cached.get("title") or "",
            h1s=list(cached.get("h1s") or []),
            h2s=list(cached.get("h2s") or []),
            meta_description=cached.get("meta_description") or "",
            canonical=cached.get("canonical") or "",
            word_count=int(cached.get("word_count") or 0),
            load_time=load_time,
            images=[
                ImageInfo(src=img.get("src", ""), alt=img.get("alt"))
                for img in (cached.get("images") or [])
            ],
            internal_links=list(cached.get("internal_links") or []),
            external_links=list(cached.get("external_links") or []),
            is_redirect=bool(cached.get("is_redirect")),
            redirect_chain=list(cached.get("redirect_chain") or []),
            content_snippet=cached.get("content_snippet") or "",
            error=None,
            etag=cached.get("etag") or "",
            last_modified=cached.get("last_modified") or "",
            from_cache=True,
        )

    def _fetch(self, url: str, conditional: bool = True) -> PageData:
        page = PageData(url=url)
        cached = self.cached_pages.get(self._normalize(url)) if conditional else None
        headers = {}
        if cached:
            if cached.get("etag"):
                headers["If-None-Match"] = cached["etag"]
            if cached.get("last_modified"):
                headers["If-Modified-Since"] = cached["last_modified"]

        self.limiter.acquire()
        t0 = time.time()
        try:
            refetch_plain = False
            html = None
            base_url = url

            with self.session.get(
                url,
                headers=headers or None,
                timeout=self.timeout,
                allow_redirects=True,
                stream=True,
            ) as resp:
                page.load_time = time.time() - t0
                page.status_code = resp.status_code
                self.limiter.on_response(resp.status_code)

                if resp.history:
                    page.is_redirect = True
                    page.redirect_chain = [r.url for r in resp.history] + [resp.url]

                if resp.status_code == 304:
                    # Unchanged: reuse the stored record wholesale, keeping its
                    # 200 status so the SEO audit does not see a phantom "304".
                    if cached and cached.get("status_code"):
                        return self._page_from_cache(cached, url, page.load_time)
                    # We revalidated but have no usable record to reuse, so ask
                    # again plainly. If we never sent validators in the first
                    # place, re-asking is the identical request — report as-is.
                    refetch_plain = bool(headers)
                else:
                    page.etag = (resp.headers.get("ETag") or "").strip()
                    page.last_modified = (resp.headers.get("Last-Modified") or "").strip()

                    if "text/html" in resp.headers.get("content-type", "").lower():
                        html = resp.text
                        # Relative links/images must resolve against the URL the
                        # content actually came from. A directory URL like
                        # /divisions/kiryluk 301s to /divisions/kiryluk/, and
                        # resolving "research.php" against the pre-redirect form
                        # silently drops the folder.
                        base_url = resp.url or url

            if refetch_plain:
                return self._fetch(url, conditional=False)

            if html is not None:
                self._parse(page, html, base_url)

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

        # Images — extracted before boilerplate stripping below
        for img in soup.find_all("img"):
            src_val = img.get("src", "")
            src = (src_val[0] if isinstance(src_val, list) else src_val).strip()
            if not src or src.startswith("data:"):
                continue
            abs_src = urljoin(base_url, src)
            alt_val = img.get("alt", None)
            alt = alt_val[0] if isinstance(alt_val, list) else alt_val # type: ignore
            page.images.append(ImageInfo(src=abs_src, alt=alt))

        # Links — extracted before boilerplate stripping below, since nav/header/
        # footer menus (which get decompose()'d for the word count) are often the
        # only place a site links out to its subfolders
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

        # Word count — strip boilerplate first
        for tag in soup(["script", "style", "nav", "footer", "header", "aside", "noscript"]):
            tag.decompose()
        body = soup.find("body")
        if body:
            text = body.get_text(separator=" ", strip=True)
            words = text.split()
            page.word_count = len(words)
            page.content_snippet = " ".join(words[:120])  # ~600 chars for AI prompts
