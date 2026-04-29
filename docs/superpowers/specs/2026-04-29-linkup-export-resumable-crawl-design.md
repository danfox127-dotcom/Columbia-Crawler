# Design: LinkUpAI Export + Resumable Crawl

**Date:** 2026-04-29
**Scope:** `content_ct` only (`Columbia-Crawler` repo)
**Status:** Approved — ready for implementation

---

## Problem

`content_ct` and `LinkUpAI` are separate tools that both crawl the same sites independently. Every time a site needs both an SEO audit and an internal-link analysis, the same crawl runs twice. There's also no way to resume a crawl that was interrupted mid-run.

## Goals

1. Define a stable, versioned JSONL export schema that `content_ct` produces and `LinkUpAI` (and future tools) can consume — eliminating the double-crawl.
2. Add a "Download for LinkUpAI" export button to the Streamlit UI.
3. Add a "Resume from previous crawl" option so interrupted crawls don't start from scratch.

## Non-Goals

- Changes to `LinkUpAI` / `SEOLinkUp` (separate spec).
- A live "Send to LinkUpAI" hand-off (add after file-based flow is validated in practice).
- JS rendering, image perceptual hashing, Google Search Console integration.
- Extracting a shared library across apps.

---

## Schema: `linkup_export.v1`

Format: **JSONL**. Line 1 is a header object. Lines 2..N are page rows.

### Line 1 — header

```json
{
  "kind": "header",
  "schema_version": "linkup_export.v1",
  "source_app": "content_ct",
  "source_app_version": "0.x.y",
  "generated_at": "2026-04-29T14:32:00Z",
  "start_url": "https://www.example-site.edu",
  "crawl_mode": "bfs",
  "max_pages": 1000,
  "pages_crawled": 847,
  "exclude_paths": ["/private/"],
  "include_paths": []
}
```

### Lines 2..N — page rows

```json
{
  "kind": "page",
  "url": "https://www.example-site.edu/some-page",
  "status_code": 200,
  "title": "Page Title | Site Name",
  "h1s": ["Page Title"],
  "h2s": ["Section One", "Section Two"],
  "meta_description": "Description text...",
  "canonical": "https://www.example-site.edu/some-page",
  "word_count": 842,
  "content_snippet": "First 120 words of body content...",
  "internal_links": ["https://www.example-site.edu/other-page"],
  "external_links": ["https://www.external-domain.com/"],
  "is_redirect": false,
  "redirect_chain": [],
  "images": [{"src": "https://www.example-site.edu/img.jpg", "alt": "Description"}],
  "load_time": 0.42,
  "error": null
}
```

### Contract rules

| Rule | Detail |
|---|---|
| Versioning | `schema_version` = `linkup_export.v1`. Breaking changes bump major (`v2`). Additive fields do not. |
| Forward compat | Consumers MUST ignore unknown fields. |
| Required fields (header) | `kind`, `schema_version`, `source_app`, `start_url`, `generated_at` |
| Required fields (page) | `kind`, `url`, `status_code` |
| Null vs absent | `null` = known-absent (e.g. `error: null`). `alt: null` = attribute missing; `alt: ""` = explicitly empty. Empty lists = `[]`, never `null`. |
| URL normalization | All URLs normalized via `Crawler._normalize` (no fragments, no trailing slash). |

### What is NOT in the schema

- Audit findings / severity codes from `auditor.py` — audit rules evolve; raw crawl data must stay stable.
- AI-generated suggestions from `ai_advisor.py` — these are derived, not source data.
- Perceptual image hashes — that's `imagecheck`'s responsibility.

---

## Changes by file

### `crawler.py` — two small additions

**1. `PageData.to_dict()`**

Add a serialization method to the existing `PageData` dataclass:

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

**2. `Crawler.__init__` — `seed_visited` parameter**

Add one optional parameter:

```python
def __init__(self, ..., seed_visited: Optional[set] = None):
    ...
    self.visited: set[str] = seed_visited or set()
```

The existing BFS loop in `crawl()` already checks `if url in self.visited` — no other changes needed. The queue re-discovers naturally from `start_url` via BFS.

### `schemas/linkup_export_v1.py` — new file

Single source of truth for the schema. Contains:
- `build_header(crawler, crawl_mode, pages_crawled)` — returns the header dict.
- `build_export_jsonl(header_dict, page_dicts)` — returns a newline-joined string ready for download.
- `parse_export_jsonl(file_content)` — parses a JSONL string, returns `(header_dict, list[page_dict])`. Used by the resume flow.
- `SOURCE_APP_VERSION` constant.

### `app.py` — two UI additions (~50 lines total)

**Resume uploader (input side)**

On the crawl configuration form, below existing inputs:

```
[ Upload previous crawl JSONL to resume (optional) ]
```

- Parse uploaded file via `parse_export_jsonl`.
- Extract URL set → pass as `seed_visited` to `Crawler.__init__`.
- Show info badge: `"Resuming — skipping {n} already-crawled pages."`
- Mismatch warning (non-blocking): if uploaded `start_url` ≠ current input URL, warn the user.
- On parse failure: show error, proceed as fresh crawl.

**Export button (output side)**

On the audit results tab, alongside the existing CSV export:

```
[ ⬇ Download CSV ]   [ ⬇ Export for LinkUpAI (JSONL) ]
```

- Builds JSONL via `build_export_jsonl`.
- Uses `st.download_button` — no server-side file write.
- Filename: `{netloc}_linkup_export_{YYYY-MM-DD}.jsonl`
- Available immediately after crawl completes; does not require AI advisor to have run.

### `docs/linkup_export_schema.md` — new file

Human-readable schema reference with field descriptions and a worked example. This is the document the LinkUpAI spec will reference when implementing the ingest path.

---

## Testing

No formal test suite. Three manual checks:

| Check | Steps | Pass criteria |
|---|---|---|
| Schema round-trip | Crawl 5 pages, export JSONL, run `python3 -c "import json; [json.loads(l) for l in open('f.jsonl')]"` | Exits clean |
| Resume | Crawl 10 pages, export. Upload as resume file, re-crawl same URL. | "Skipping N pages" badge appears; second run is faster |
| Edge cases | Crawl a 404 URL and a page with no H1. | JSONL row produced for each; no crash |

---

## Future (not in this spec)

- **Live hand-off:** "Send to LinkUpAI" button that writes to a shared HF Dataset slot or constructs a query-param import URL. Add once the file-based flow is validated.
- **LinkUpAI ingest path:** Separate spec. LinkUpAI accepts `linkup_export.v1` JSONL upload and skips its own sitemap scan when it's provided.
- **Queue seeding on resume:** Pre-populate BFS queue with discovered links from previous run, not just `visited`. Useful only if hitting the 20k cap mid-crawl. Defer.
