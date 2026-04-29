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
