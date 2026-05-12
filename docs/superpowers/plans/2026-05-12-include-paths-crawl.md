# Include Paths (Crawl Mode) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an "Include paths" sidebar control that limits BFS crawling to URLs matching at least one specified path segment.

**Architecture:** `crawler.py` already implements `include_paths` in `Crawler._is_crawlable`. All changes are in `app.py`: restructure the sidebar so path filter textareas are mode-specific, add the new include textarea to crawl mode, parse and forward `include_paths` to `BFSCrawler`, and fix a hardcoded `[]` in `_render_linkup_export_button`.

**Tech Stack:** Python, Streamlit, existing `Crawler` class

---

## File Map

| File | Action | Responsibility |
|------|--------|----------------|
| `tests/test_crawler_additions.py` | Modify | Add unit tests for `include_paths` filtering in `Crawler._is_crawlable` |
| `app.py` | Modify | Sidebar restructure + include_paths wiring |

---

### Task 1: Test `include_paths` behavior in `Crawler._is_crawlable`

**Files:**
- Modify: `tests/test_crawler_additions.py`

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_crawler_additions.py`:

```python
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
```

- [ ] **Step 2: Run the tests to verify they pass** (logic already in `crawler.py`)

```bash
pytest tests/test_crawler_additions.py -v -k "include_paths"
```

Expected: all 5 new tests PASS (the backend logic is already implemented).

- [ ] **Step 3: Commit**

```bash
git add tests/test_crawler_additions.py
git commit -m "test: add include_paths crawlability unit tests"
```

---

### Task 2: Restructure sidebar — move Exclude paths into mode blocks

**Files:**
- Modify: `app.py:269-276` (the exclude paths textarea currently outside both mode branches)

The current sidebar structure is roughly:

```
if mode == "🕷️ Crawl Site":
    ...inputs...
else:
    ...inputs...

st.text_area("Exclude paths ...", key="exclude_paths_raw", ...)  # ← move this
start_button = st.button(...)
```

- [ ] **Step 1: Move the exclude textarea into both mode branches**

In `app.py`, delete the standalone exclude textarea (lines ~269-275) and add it at the **end** of each mode branch. The crawl branch ends before the `else:` at the resume uploader block (~line 260); the sitemap branch ends before the closing of `with st.sidebar:`.

After the change the sidebar block should look like:

```python
with st.sidebar:
    st.header("⚙️ Settings")
    mode = st.radio("Input mode", ["🕷️ Crawl Site", "🗺️ Scan Sitemap"], horizontal=True)

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
        st.text_area(
            "Exclude paths (one per line)",
            key="exclude_paths_raw",
            placeholder="/news/\n/events/\n/blog/",
            help="Top-level folder names to skip, e.g. /news/",
            height=100,
        )
        st.text_area(
            "Include paths — scan ONLY these (one per line)",
            key="include_paths_raw",
            placeholder="/faculty/\n/research/\n/departments/",
            help="Only crawl URLs whose path contains one of these. Leave blank to crawl everything.",
            height=100,
        )
    else:
        target_url = st.text_input("Sitemap URL", value="https://vagelos.columbia.edu/sitemap.xml")
        max_pages_input = st.number_input(
            "Max URLs to check (0 = all)",
            min_value=0, value=1000, step=500,
            help="~1k ≈ 2 min | ~5k ≈ 10 min | ~20k ≈ 35 min (10 threads)"
        )
        st.text_area(
            "Exclude paths (one per line)",
            key="exclude_paths_raw",
            placeholder="/news/\n/events/\n/blog/",
            help="Top-level folder names to skip, e.g. /news/ — applies to sitemap scan",
            height=100,
        )

    start_button = st.button("🚀 Start", use_container_width=True)
    st.divider()
    st.header("🤖 Gemini Settings")
    gemini_key = st.text_input(
        "Gemini API Key", type="password",
        value=os.environ.get("GEMINI_API_KEY", ""),
        help="Set GEMINI_API_KEY in HF Secrets or paste here"
    )
```

- [ ] **Step 2: Run the app briefly to verify no import/syntax errors**

```bash
cd /Users/danweiman/Documents/GitHub/Columbia-Crawler/.claude/worktrees/zen-bardeen-4795cd
python -c "import ast; ast.parse(open('app.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add app.py
git commit -m "refactor: move exclude paths into mode branches, add include paths textarea"
```

---

### Task 3: Wire `include_paths` into the execution block and fix linkup export

**Files:**
- Modify: `app.py` — execution block (~line 291) and `_render_linkup_export_button` (~line 189)

- [ ] **Step 1: Parse `include_paths` in the execution block**

In the `if start_button:` block, the current excluded_paths parse line is:

```python
excluded_paths = [p for p in st.session_state.get("exclude_paths_raw", "").splitlines() if p.strip()]
```

Add the include_paths parse immediately after it:

```python
include_paths = [p for p in st.session_state.get("include_paths_raw", "").splitlines() if p.strip()]
```

- [ ] **Step 2: Pass `include_paths` to `BFSCrawler`**

The current crawler instantiation is:

```python
crawler_obj = BFSCrawler(
    target_url,
    max_pages=int(max_pages_input) if max_pages_input > 0 else 20000,
    delay=0.1,
    exclude_paths=excluded_paths,
    seed_visited=seed if seed else None,
)
```

Change to:

```python
crawler_obj = BFSCrawler(
    target_url,
    max_pages=int(max_pages_input) if max_pages_input > 0 else 20000,
    delay=0.1,
    exclude_paths=excluded_paths,
    include_paths=include_paths,
    seed_visited=seed if seed else None,
)
```

- [ ] **Step 3: Add `include_paths` to `crawl_meta`**

The current `crawl_meta` dict is:

```python
st.session_state.crawl_meta = {
    "start_url": target_url,
    "crawl_mode": "bfs",
    "max_pages": int(max_pages_input) if max_pages_input > 0 else 20000,
    "exclude_paths": excluded_paths,
}
```

Change to:

```python
st.session_state.crawl_meta = {
    "start_url": target_url,
    "crawl_mode": "bfs",
    "max_pages": int(max_pages_input) if max_pages_input > 0 else 20000,
    "exclude_paths": excluded_paths,
    "include_paths": include_paths,
}
```

- [ ] **Step 4: Fix `_render_linkup_export_button` to read `include_paths` from meta**

In `_render_linkup_export_button`, the current `build_header` call has:

```python
include_paths=[],
```

Change to:

```python
include_paths=meta.get("include_paths", []),
```

- [ ] **Step 5: Syntax check**

```bash
python -c "import ast; ast.parse(open('app.py').read()); print('OK')"
```

Expected: `OK`

- [ ] **Step 6: Commit**

```bash
git add app.py
git commit -m "feat: wire include_paths into BFS crawler and linkup export meta"
```
