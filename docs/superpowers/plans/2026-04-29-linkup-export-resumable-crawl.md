# LinkUpAI Export + Resumable Crawl Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a versioned JSONL export for LinkUpAI and a resume-from-previous-crawl option to content_ct, while wiring `crawler.py`'s `Crawler` class into `app.py`'s crawl mode.

**Architecture:** A new `schemas/linkup_export_v1.py` module defines the shared data contract as pure functions (no app or crawler dependencies). `crawler.py` gets `PageData.to_dict()` for stable serialization and a `seed_visited` parameter for resumable crawls. `app.py`'s "Crawl Site" mode is rewired to use `Crawler` from `crawler.py` (replacing the dead Scrapy/requests path), and tab1 gains an "Export for LinkUpAI" download button alongside the existing CSV button.

**Tech Stack:** Python 3.8+, Streamlit, `crawler.py` (BFS, requests + BS4), `schemas/linkup_export_v1.py` (new), pytest (dev only)

**Important discovery:** `app.py` currently does NOT use `crawler.py`. It has its own `crawl_with_requests` fallback and a Scrapy subprocess path — both are dead code candidates that this plan replaces. The `Crawler` class in `crawler.py` is strictly superior to both.

---

## File Map

| Action | Path | Responsibility |
|---|---|---|
| Create | `schemas/__init__.py` | Package marker (empty) |
| Create | `schemas/linkup_export_v1.py` | Schema contract: build_header, build_export_jsonl, parse_export_jsonl |
| Create | `tests/__init__.py` | Package marker (empty) |
| Create | `tests/test_schema.py` | Unit tests for schema module |
| Create | `tests/test_crawler_additions.py` | Unit tests for PageData.to_dict() and seed_visited |
| Modify | `crawler.py` | Add PageData.to_dict(); add seed_visited to Crawler.__init__ |
| Modify | `app.py` | Wire Crawler; add resume uploader; add export button; remove dead code |
| Create | `docs/linkup_export_schema.md` | Human-readable schema reference |

---

## Task 1: Create `schemas/linkup_export_v1.py`

**Files:**
- Create: `schemas/__init__.py`
- Create: `schemas/linkup_export_v1.py`
- Create: `tests/__init__.py`
- Create: `tests/test_schema.py`

- [ ] **Step 1.1: Create `schemas/__init__.py` (empty)**

```
schemas/__init__.py  ← empty file, just touch it
```

Run: `touch schemas/__init__.py`

- [ ] **Step 1.2: Write the failing tests first**

Create `tests/__init__.py` (empty), then create `tests/test_schema.py`:

```python
import json
import pytest
from schemas.linkup_export_v1 import (
    build_header,
    build_export_jsonl,
    parse_export_jsonl,
    SCHEMA_VERSION,
    SOURCE_APP,
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


def test_build_header_exclude_paths():
    h = build_header("https://example.com", "sitemap", 500, 400, ["/news/", "/events/"], [])
    assert h["exclude_paths"] == ["/news/", "/events/"]
    assert h["include_paths"] == []


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
```

- [ ] **Step 1.3: Run tests — confirm they fail with ImportError**

```bash
python -m pytest tests/test_schema.py -v
```

Expected: `ModuleNotFoundError: No module named 'schemas'`

(If pytest is not installed: `pip install pytest` first)

- [ ] **Step 1.4: Create `schemas/linkup_export_v1.py`**

```python
import json
from datetime import datetime, timezone
from typing import Dict, List, Optional, Tuple

SOURCE_APP = "content_ct"
SOURCE_APP_VERSION = "1.0.0"
SCHEMA_VERSION = "linkup_export.v1"


def build_header(
    start_url: str,
    crawl_mode: str,
    max_pages: int,
    pages_crawled: int,
    exclude_paths: List[str],
    include_paths: List[str],
) -> dict:
    return {
        "kind": "header",
        "schema_version": SCHEMA_VERSION,
        "source_app": SOURCE_APP,
        "source_app_version": SOURCE_APP_VERSION,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "start_url": start_url,
        "crawl_mode": crawl_mode,
        "max_pages": max_pages,
        "pages_crawled": pages_crawled,
        "exclude_paths": exclude_paths,
        "include_paths": include_paths,
    }


def build_export_jsonl(header_dict: dict, page_dicts: List[dict]) -> str:
    lines = [json.dumps(header_dict, ensure_ascii=False)]
    for page in page_dicts:
        lines.append(json.dumps(page, ensure_ascii=False))
    return "\n".join(lines)


def parse_export_jsonl(file_content: str) -> Tuple[Optional[dict], List[dict]]:
    header: Optional[dict] = None
    pages: List[dict] = []
    for line in file_content.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        kind = obj.get("kind")
        if kind == "header":
            header = obj
        elif kind == "page":
            pages.append(obj)
    return header, pages
```

- [ ] **Step 1.5: Run tests — confirm they pass**

```bash
python -m pytest tests/test_schema.py -v
```

Expected: all 8 tests PASS

- [ ] **Step 1.6: Commit**

```bash
git add schemas/__init__.py schemas/linkup_export_v1.py tests/__init__.py tests/test_schema.py
git commit -m "feat: add linkup_export_v1 schema module with tests"
```

---

## Task 2: Extend `crawler.py`

**Files:**
- Modify: `crawler.py` (PageData class ~line 27, Crawler.__init__ ~line 61)
- Create: `tests/test_crawler_additions.py`

- [ ] **Step 2.1: Write the failing tests**

Create `tests/test_crawler_additions.py`:

```python
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
```

- [ ] **Step 2.2: Run tests — confirm they fail**

```bash
python -m pytest tests/test_crawler_additions.py -v
```

Expected: `AttributeError: 'PageData' object has no attribute 'to_dict'` and `TypeError: __init__() got an unexpected keyword argument 'seed_visited'`

- [ ] **Step 2.3: Add `to_dict()` to `PageData` in `crawler.py`**

In `crawler.py`, find the `PageData` dataclass (ends around line 43 before the blank line). Add `to_dict()` as a regular method after the field definitions:

```python
    def to_dict(self) -> dict:
        return {
            "kind": "page",
            "url": self.url,
            "status_code": self.status_code,
            "title": self.title,
            "h1s": self.h1s,
            "h2s": self.h2s,
            "meta_description": self.meta_description,
            "canonical": self.canonical,
            "word_count": self.word_count,
            "content_snippet": self.content_snippet,
            "internal_links": self.internal_links,
            "external_links": self.external_links,
            "is_redirect": self.is_redirect,
            "redirect_chain": self.redirect_chain,
            "images": [{"src": img.src, "alt": img.alt} for img in self.images],
            "load_time": round(self.load_time, 3),
            "error": self.error,
        }
```

The full updated `PageData` block in `crawler.py` should look like:

```python
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

    def to_dict(self) -> dict:
        return {
            "kind": "page",
            "url": self.url,
            "status_code": self.status_code,
            "title": self.title,
            "h1s": self.h1s,
            "h2s": self.h2s,
            "meta_description": self.meta_description,
            "canonical": self.canonical,
            "word_count": self.word_count,
            "content_snippet": self.content_snippet,
            "internal_links": self.internal_links,
            "external_links": self.external_links,
            "is_redirect": self.is_redirect,
            "redirect_chain": self.redirect_chain,
            "images": [{"src": img.src, "alt": img.alt} for img in self.images],
            "load_time": round(self.load_time, 3),
            "error": self.error,
        }
```

- [ ] **Step 2.4: Add `seed_visited` parameter to `Crawler.__init__`**

In `crawler.py`, find `Crawler.__init__` (starts around line 61). Add `seed_visited` as the last parameter and update the `self.visited` assignment.

Change the signature from:
```python
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
```

To:
```python
    def __init__(
        self,
        start_url: str,
        max_pages: int = 100,
        delay: float = 0.5,
        respect_robots: bool = True,
        timeout: int = 10,
        exclude_paths: Optional[List[str]] = None,
        include_paths: Optional[List[str]] = None,
        seed_visited: Optional[set] = None,
    ):
```

Then change the line:
```python
        self.visited: "set[str]" = set()
```

To:
```python
        self.visited: "set[str]" = set(seed_visited) if seed_visited else set()
```

- [ ] **Step 2.5: Run tests — confirm they pass**

```bash
python -m pytest tests/test_crawler_additions.py -v
```

Expected: all 6 tests PASS

- [ ] **Step 2.6: Run all tests to confirm nothing broke**

```bash
python -m pytest tests/ -v
```

Expected: all 14 tests PASS

- [ ] **Step 2.7: Commit**

```bash
git add crawler.py tests/test_crawler_additions.py
git commit -m "feat: add PageData.to_dict() and seed_visited to Crawler"
```

---

## Task 3: Wire `Crawler` into `app.py` + resume uploader

**Files:**
- Modify: `app.py`

This task removes dead code (Scrapy path + `crawl_with_requests`), wires in `Crawler` from `crawler.py`, adds session state keys for the new features, and adds the resume file uploader to the sidebar.

- [ ] **Step 3.1: Update imports at the top of `app.py`**

Replace lines 1–13 (current imports block) with:

```python
import streamlit as st
import pandas as pd
import os
import json
import requests
import xml.etree.ElementTree as ET
from bs4 import BeautifulSoup
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.parse import urlparse, urljoin
from crawler import Crawler as BFSCrawler
from schemas.linkup_export_v1 import build_header, build_export_jsonl, parse_export_jsonl
```

Removed: `io`, `sys`, `subprocess`, `deque` (from collections), `urldefrag`. Added: `BFSCrawler`, schema imports.

- [ ] **Step 3.2: Remove dead code functions**

Delete the following two functions entirely from `app.py`:

- `create_spider_script` (lines 23–91, the `# --- 3. SCRAPY SPIDER SCRIPT GENERATOR ---` section)
- `crawl_with_requests` (lines 94–153, the `# --- 4. REQUESTS FALLBACK CRAWLER ---` section)

After deletion, the file should jump from the `# --- 2. CONSTANTS ---` block directly to `# --- 5. SITEMAP SCANNER ---`.

- [ ] **Step 3.3: Update session state initialization**

Find this block (currently around line 321 after the deletions):
```python
for key in ('df', 'issues_df', 'gemini_response'):
    if key not in st.session_state:
        st.session_state[key] = None
```

Replace with:
```python
for key in ('df', 'issues_df', 'gemini_response', 'crawl_pages', 'crawl_meta', 'resume_pages'):
    if key not in st.session_state:
        st.session_state[key] = None
```

- [ ] **Step 3.4: Add resume file uploader to sidebar**

Find this block in the sidebar (inside `if mode == "🕷️ Crawl Site":`):
```python
    if mode == "🕷️ Crawl Site":
        target_url = st.text_input("Start URL", value="https://vagelos.columbia.edu")
        max_pages_input = st.number_input(
            "Max pages (0 = unlimited)",
            min_value=0, value=500, step=100,
            help="~500 pages ≈ 30s | ~5k ≈ 5 min | ~20k ≈ 20 min with Scrapy"
        )
```

Replace with:
```python
    if mode == "🕷️ Crawl Site":
        target_url = st.text_input("Start URL", value="https://vagelos.columbia.edu")
        max_pages_input = st.number_input(
            "Max pages (0 = unlimited)",
            min_value=0, value=500, step=100,
            help="~500 pages ≈ 30s | ~5k ≈ 5 min | ~20k ≈ 20 min"
        )
        resume_file = st.file_uploader(
            "Resume from previous crawl (optional)",
            type=["jsonl"],
            help="Upload a previous LinkUpAI export JSONL to skip already-crawled pages.",
        )
        if resume_file is not None:
            try:
                _, resume_pages = parse_export_jsonl(resume_file.read().decode("utf-8"))
                st.session_state.resume_pages = resume_pages
            except Exception:
                st.warning("Could not parse resume file — starting a fresh crawl.")
                st.session_state.resume_pages = None
        else:
            st.session_state.resume_pages = None
```

- [ ] **Step 3.5: Replace the crawl execution block**

Find the current crawl execution inside `if start_button:` → `if mode == "🕷️ Crawl Site":` (currently lines 373–392 before deletions, now shifted). The block looks like:

```python
        if mode == "🕷️ Crawl Site":
            with st.spinner(f"Crawling {target_url}..."):
                try:
                    import scrapy  # type: ignore
                ... (all of it through) ...
            if os.path.exists(output_jsonl) and os.path.getsize(output_jsonl) > 0:
                with open(output_jsonl, 'r', encoding='utf-8') as f:
                    st.session_state.df = pd.read_json(io.StringIO(f.read()), lines=True)
```

Replace the entire `if mode == "🕷️ Crawl Site":` block with:

```python
        if mode == "🕷️ Crawl Site":
            seed: set = set()
            if st.session_state.resume_pages:
                seed = {p["url"] for p in st.session_state.resume_pages if p.get("url")}
                st.info(f"Resuming — skipping {len(seed)} already-crawled pages.")

            crawler_obj = BFSCrawler(
                target_url,
                max_pages=int(max_pages_input) if max_pages_input > 0 else 20000,
                delay=0.1,
                exclude_paths=excluded_paths,
                seed_visited=seed if seed else None,
            )

            progress_bar = st.progress(0, text="Starting crawl…")
            page_dicts: list = []
            rows: list = []

            try:
                for page, done, remaining in crawler_obj.crawl():
                    page_dicts.append(page.to_dict())
                    rows.append({
                        "url": page.url,
                        "status": page.status_code,
                        "title": page.title,
                        "h1": page.h1s[0] if page.h1s else "",
                        "meta_desc": page.meta_description,
                        "word_count": page.word_count,
                    })
                    total_est = done + remaining
                    progress_bar.progress(
                        done / max(total_est, 1),
                        text=f"Crawled {done} page(s)…",
                    )
            except Exception as e:
                st.error(f"Crawler error: {e}")

            progress_bar.empty()

            if rows:
                st.session_state.df = pd.DataFrame(rows)
                st.session_state.crawl_pages = page_dicts
                st.session_state.crawl_meta = {
                    "start_url": target_url,
                    "crawl_mode": "bfs",
                    "max_pages": int(max_pages_input) if max_pages_input > 0 else 20000,
                    "exclude_paths": excluded_paths,
                }
```

- [ ] **Step 3.6: Update the sitemap branch to store crawl_meta**

Find the sitemap results block inside `if start_button:` → `else:` (sitemap mode). Find where `st.session_state.df = df_sitemap` is set and add two lines after it:

```python
                if not df_sitemap.empty:
                    st.session_state.df = df_sitemap
                    st.session_state.crawl_pages = None
                    st.session_state.crawl_meta = {
                        "start_url": target_url,
                        "crawl_mode": "sitemap",
                        "max_pages": int(max_pages_input) if max_pages_input > 0 else 999999,
                        "exclude_paths": excluded_paths,
                    }
```

- [ ] **Step 3.7: Remove now-unused `output_jsonl` variable**

Find and delete this line (it was only used by the old crawl path):
```python
output_jsonl = "crawl_output.jsonl"
```

- [ ] **Step 3.8: Manual smoke test — confirm crawl mode works**

Start the app:
```bash
streamlit run app.py
```

- Set mode to "🕷️ Crawl Site", enter `https://example.com`, set max pages = 5, click Start.
- Confirm: progress bar appears and advances, results load in tab1.
- Confirm: no errors in terminal.
- Stop the app (Ctrl+C).

- [ ] **Step 3.9: Commit**

```bash
git add app.py
git commit -m "feat: wire Crawler into app.py crawl mode; add resume uploader"
```

---

## Task 4: Add "Export for LinkUpAI" button

**Files:**
- Modify: `app.py`

- [ ] **Step 4.1: Add `_render_linkup_export_button` helper function**

In `app.py`, add this function just before the `# --- 8. APP LAYOUT & UI ---` comment (i.e., after all the other helper functions):

```python
# --- LINKUP EXPORT HELPER ---
def _render_linkup_export_button(df, crawl_pages, crawl_meta):
    from datetime import date as _date
    if df is None or len(df) == 0:
        return
    meta = crawl_meta or {}
    header = build_header(
        start_url=meta.get("start_url", df["url"].iloc[0] if len(df) > 0 else ""),
        crawl_mode=meta.get("crawl_mode", "unknown"),
        max_pages=meta.get("max_pages", len(df)),
        pages_crawled=len(df),
        exclude_paths=meta.get("exclude_paths", []),
        include_paths=[],
    )
    if crawl_pages:
        page_dicts = crawl_pages
    else:
        page_dicts = [
            {
                "kind": "page",
                "url": str(row.get("url", "")),
                "status_code": int(row.get("status", 0) or 0),
                "title": str(row.get("title", "") or ""),
                "h1s": [row["h1"]] if row.get("h1") else [],
                "h2s": [],
                "meta_description": str(row.get("meta_desc", "") or ""),
                "canonical": "",
                "word_count": int(row.get("word_count", 0) or 0),
                "content_snippet": "",
                "internal_links": [],
                "external_links": [],
                "is_redirect": False,
                "redirect_chain": [],
                "images": [],
                "load_time": None,
                "error": None,
            }
            for _, row in df.iterrows()
        ]
    netloc = urlparse(df["url"].iloc[0]).netloc.replace(".", "_") if len(df) > 0 else "site"
    filename = f"{netloc}_linkup_export_{_date.today()}.jsonl"
    jsonl_bytes = build_export_jsonl(header, page_dicts).encode("utf-8")
    st.download_button(
        "⬇ Export for LinkUpAI (JSONL)",
        jsonl_bytes,
        file_name=filename,
        mime="application/jsonl",
        use_container_width=True,
    )
```

- [ ] **Step 4.2: Update tab1 to use two-column download buttons**

Find tab1 (currently):
```python
    with tab1:
        st.success(f"✅ {len(df)} pages scanned.")
        st.dataframe(df, use_container_width=True)
        st.download_button("Download CSV", df.to_csv(index=False).encode('utf-8'),
                           file_name="crawl_results.csv", mime="text/csv")
```

Replace with:
```python
    with tab1:
        st.success(f"✅ {len(df)} pages scanned.")
        st.dataframe(df, use_container_width=True)
        col_dl1, col_dl2 = st.columns(2)
        with col_dl1:
            st.download_button(
                "⬇ Download CSV",
                df.to_csv(index=False).encode("utf-8"),
                file_name="crawl_results.csv",
                mime="text/csv",
                use_container_width=True,
            )
        with col_dl2:
            _render_linkup_export_button(
                df,
                st.session_state.crawl_pages,
                st.session_state.crawl_meta,
            )
```

- [ ] **Step 4.3: Manual smoke test — confirm export button works**

Start the app:
```bash
streamlit run app.py
```

- Crawl `https://example.com` (5 pages), wait for results.
- In tab1, confirm two buttons appear: "⬇ Download CSV" and "⬇ Export for LinkUpAI (JSONL)".
- Click "⬇ Export for LinkUpAI (JSONL)" and save the file.
- Validate the file:
  ```bash
  python3 -c "
  import json
  lines = open('example_com_linkup_export_$(date +%F).jsonl').readlines()
  objs = [json.loads(l) for l in lines]
  print('Lines:', len(objs))
  print('Header:', objs[0].get('schema_version'))
  print('First page URL:', objs[1].get('url'))
  print('First page internal_links count:', len(objs[1].get('internal_links', [])))
  "
  ```
  Expected: `schema_version: linkup_export.v1`, page URLs present, `internal_links` is a list.

- [ ] **Step 4.4: Manual smoke test — confirm resume works**

- Take the JSONL file downloaded above.
- Start a new crawl of `https://example.com`, upload the JSONL via the resume uploader, set max pages = 10, click Start.
- Confirm: "Resuming — skipping N already-crawled pages." message appears.
- Confirm: crawl completes with fewer (or zero) pages fetched.

- [ ] **Step 4.5: Commit**

```bash
git add app.py
git commit -m "feat: add Export for LinkUpAI button to tab1"
```

---

## Task 5: Add schema reference doc

**Files:**
- Create: `docs/linkup_export_schema.md`

- [ ] **Step 5.1: Create `docs/linkup_export_schema.md`**

```markdown
# LinkUpAI Export Schema — `linkup_export.v1`

This document is the canonical reference for the JSONL format produced by content_ct's "Export for LinkUpAI" feature.

## Format

JSONL (JSON Lines): one JSON object per line. Line 1 is always a header object. Lines 2..N are page rows.

## Contract rules

- **Schema versioning:** `schema_version` is a string. Breaking changes increment the major version (`v2`). Adding new optional fields does NOT change the version.
- **Forward compatibility:** Consumers MUST ignore unknown fields.
- **Null vs absent:** `null` means the field is known to be absent. `alt: null` on an image means the `alt` attribute was missing. `alt: ""` means it was explicitly empty. Empty lists are `[]`, never `null`.
- **URL normalization:** All URLs are normalized (no fragments, no trailing slash).

## Header object (line 1)

| Field | Type | Required | Notes |
|---|---|---|---|
| `kind` | string | yes | Always `"header"` |
| `schema_version` | string | yes | Always `"linkup_export.v1"` |
| `source_app` | string | yes | Always `"content_ct"` |
| `source_app_version` | string | yes | content_ct version |
| `generated_at` | string | yes | ISO 8601 UTC timestamp |
| `start_url` | string | yes | The URL the crawl started from |
| `crawl_mode` | string | yes | `"bfs"` or `"sitemap"` |
| `max_pages` | integer | yes | Page cap set in the UI |
| `pages_crawled` | integer | yes | Actual pages in this file |
| `exclude_paths` | array | yes | Path prefixes excluded from crawl |
| `include_paths` | array | yes | Path prefixes required (empty = all) |

## Page row (lines 2..N)

| Field | Type | Required | Notes |
|---|---|---|---|
| `kind` | string | yes | Always `"page"` |
| `url` | string | yes | Normalized page URL |
| `status_code` | integer | yes | HTTP status (0 = connection error) |
| `title` | string | no | `<title>` text |
| `h1s` | array[string] | no | All `<h1>` texts on the page |
| `h2s` | array[string] | no | All `<h2>` texts on the page |
| `meta_description` | string | no | `<meta name="description">` content |
| `canonical` | string | no | `<link rel="canonical">` href |
| `word_count` | integer | no | Body word count (boilerplate stripped) |
| `content_snippet` | string | no | First ~120 words of body text |
| `internal_links` | array[string] | no | Absolute URLs to same-domain pages |
| `external_links` | array[string] | no | Absolute URLs to other domains |
| `is_redirect` | boolean | no | True if final URL differs from requested |
| `redirect_chain` | array[string] | no | Intermediate URLs in redirect |
| `images` | array[object] | no | See image object below |
| `load_time` | number | no | Seconds (3 decimal places), null = unknown |
| `error` | string or null | no | Error message if fetch failed |

### Image object

| Field | Type | Notes |
|---|---|---|
| `src` | string | Absolute image URL |
| `alt` | string or null | `null` = attribute absent; `""` = explicitly empty |

## Sitemap mode limitation

When content_ct is run in sitemap mode, `internal_links`, `external_links`, `h2s`, `content_snippet`, and `canonical` are empty for all page rows. Only BFS crawl mode captures the full page structure.

## Example

```json
{"kind":"header","schema_version":"linkup_export.v1","source_app":"content_ct","source_app_version":"1.0.0","generated_at":"2026-04-29T14:32:00Z","start_url":"https://www.site.edu","crawl_mode":"bfs","max_pages":1000,"pages_crawled":2,"exclude_paths":[],"include_paths":[]}
{"kind":"page","url":"https://www.site.edu/page-one","status_code":200,"title":"Page One","h1s":["Page One"],"h2s":["Overview","Details"],"meta_description":"About page one","canonical":"https://www.site.edu/page-one","word_count":350,"content_snippet":"Content starts here...","internal_links":["https://www.site.edu/page-two"],"external_links":[],"is_redirect":false,"redirect_chain":[],"images":[{"src":"https://www.site.edu/img.jpg","alt":"A diagram"}],"load_time":0.31,"error":null}
{"kind":"page","url":"https://www.site.edu/broken","status_code":404,"title":"","h1s":[],"h2s":[],"meta_description":"","canonical":"","word_count":0,"content_snippet":"","internal_links":[],"external_links":[],"is_redirect":false,"redirect_chain":[],"images":[],"load_time":0.18,"error":null}
```
```

- [ ] **Step 5.2: Commit**

```bash
git add docs/linkup_export_schema.md
git commit -m "docs: add linkup_export_v1 schema reference"
```

---

## Task 6: Manual verification (from spec)

- [ ] **Step 6.1: Schema round-trip check**

Crawl 5 pages (`https://example.com`, max=5), export the JSONL. Run:

```bash
python3 -c "
import json
with open('example_com_linkup_export_$(date +%F).jsonl') as f:
    lines = [json.loads(l) for l in f if l.strip()]
assert lines[0]['kind'] == 'header', 'No header'
assert lines[0]['schema_version'] == 'linkup_export.v1', 'Wrong version'
assert all(l['kind'] == 'page' for l in lines[1:]), 'Non-page row found'
print(f'OK — {len(lines)-1} page rows')
"
```

Expected: `OK — N page rows`

- [ ] **Step 6.2: Resume check**

```bash
# 1. Crawl 10 pages, download export as 'resume.jsonl'
# 2. Upload resume.jsonl via the resume uploader in the UI
# 3. Crawl the same URL again (max=20)
# 4. Confirm "Resuming — skipping N already-crawled pages." appears
# 5. Confirm fewer HTTP requests in terminal output
```

- [ ] **Step 6.3: Edge-case check**

Crawl a URL that includes a 404 (e.g. add `https://example.com/does-not-exist` via a known broken link), or directly crawl a site with broken links. Confirm the export still produces valid JSONL for error rows.

```bash
python3 -c "
import json
with open('example_com_linkup_export_$(date +%F).jsonl') as f:
    lines = [json.loads(l) for l in f if l.strip()]
error_pages = [l for l in lines[1:] if l.get('status_code') != 200]
print(f'Error/non-200 pages: {len(error_pages)}')
for p in error_pages:
    print(f'  {p[\"url\"]} — status {p[\"status_code\"]} error={p.get(\"error\")}')
"
```

Expected: no crash; non-200 pages appear as valid JSON rows.

- [ ] **Step 6.4: Run full test suite one final time**

```bash
python -m pytest tests/ -v
```

Expected: all 14 tests PASS

- [ ] **Step 6.5: Final commit**

```bash
git add -A
git status  # review before committing
git commit -m "feat: complete linkup export + resumable crawl implementation"
```
