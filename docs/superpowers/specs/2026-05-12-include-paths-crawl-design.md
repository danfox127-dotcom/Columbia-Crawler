# Include Paths (Crawl-Only) — Design Spec
**Date:** 2026-05-12

## Summary

Add an "Include paths" UI control to the crawler sidebar so users can whitelist specific URL path segments. Only URLs matching at least one include pattern will be crawled. Applies to BFS crawl mode only; sitemap mode is out of scope.

## Background

`crawler.py` already accepts and enforces `include_paths` in `Crawler.__init__` and `_is_crawlable`. The start URL is always allowed through regardless of include patterns. No backend changes are needed.

## Changes

### `app.py` — sidebar restructure

**Move "Exclude paths" into the crawl mode block.**
Currently the exclude textarea renders outside both mode branches (lines ~269-275). Move it inside the `if mode == "🕷️ Crawl Site":` block so crawl-specific path filters are co-located.

**Add "Include paths" textarea** directly below exclude paths inside the crawl block:
- Label: `"Include paths (scan ONLY these)"`
- Key: `"include_paths_raw"`
- Placeholder: `/faculty/\n/research/\n/departments/`
- Help: `"Only crawl URLs whose path contains one of these. Leave blank to crawl everything."`
- Height: 100

**Add "Exclude paths" textarea to sitemap mode block** so sitemap mode retains its own exclude control. Use the same key `"exclude_paths_raw"` — only one branch renders at a time, so Streamlit handles this correctly.

### Execution block (crawl mode)

Parse include paths alongside exclude paths:
```python
include_paths = [p for p in st.session_state.get("include_paths_raw", "").splitlines() if p.strip()]
```

Pass to `BFSCrawler`:
```python
crawler_obj = BFSCrawler(
    target_url,
    max_pages=...,
    delay=0.1,
    exclude_paths=excluded_paths,
    include_paths=include_paths,
    seed_visited=seed if seed else None,
)
```

Add to `crawl_meta`:
```python
"include_paths": include_paths,
```

### `_render_linkup_export_button`

The `include_paths=[]` hardcode on line ~189 should be replaced with `meta.get("include_paths", [])` so the export header reflects the actual filter used.

## What does NOT change

- `crawler.py` — no changes needed
- Sitemap scanner logic — no changes
- `_is_crawlable` behavior — start URL always passes; other URLs must match at least one include pattern if `include_paths` is non-empty
