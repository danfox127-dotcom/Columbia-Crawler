# Parallel Crawl + Conditional Requests — Design

**Date:** 2026-09-14
**Status:** Approved, pending implementation plan
**Scope:** `crawler.py`, `app.py`, `schemas/linkup_export_v1.py` (no version bump)

## Problem

Two separate performance ceilings in the BFS crawler:

1. **`crawl()` is strictly serial.** One request in flight at a time, plus a
   `time.sleep(0.1)` after every page. The crawl is network-bound — measured
   page fetches run 200–400 ms against columbiamedicine.org against ~2 ms of
   parsing — so wall-clock time is almost entirely idle waiting. Sitemap mode
   already runs 10 threads (`app.py:96`); crawl mode does not.

2. **Re-crawls refetch everything, or skip too much.** Resume works by putting
   previously-crawled URLs into `seed_visited`, so those pages are never
   fetched, never yielded, and **their links are never followed**. A resumed
   crawl therefore emits a partial report and can fail to reach pages that are
   only linked from skipped ones.

## Goals

- 4–6x wall-clock improvement on a 500-page crawl.
- Re-crawls of a known site cost roughly one cheap validation request per
  unchanged page, and produce a *complete* report.
- No change to `crawl()`'s consumer contract in `app.py`.
- Politeness controls adequate for production Columbia hosts.

## Non-goals

- asyncio/httpx rewrite. Higher ceiling, but awkward inside Streamlit's sync
  model, and the thread pool captures most of the benefit.
- Parse-level micro-optimization (lxml tuning, `SoupStrainer`). Optimizing 2 ms
  out of 300 ms.
- Vectorizing `detect_seo_issues`, response size caps, progress-bar throttling.
  Considered and deferred; see "Deferred ideas".

## §1 Rolling-window parallel fetch

`crawl()` keeps its exact signature and yield contract —
`Generator[Tuple[PageData, int, int]]` yielding `(page, pages_done,
queue_remaining)` — so `app.py`'s progress loop is untouched.

Internals:

- A `threading.Lock` guards `visited`, `queue`, and a new `claimed` counter.
- A `ThreadPoolExecutor(max_workers=N)` holds a set of in-flight futures. The
  driver tops the pool up to N by *claiming* URLs under the lock (add to
  `visited`, increment `claimed`), then blocks in
  `concurrent.futures.wait(..., return_when=FIRST_COMPLETED)`.
- As each future returns, the driver enqueues its links under the lock and
  `yield`s. **Yields happen on the consuming thread**, keeping every Streamlit
  widget call on the main thread. Workers perform only network I/O and parsing.
- `max_pages` is enforced at claim time, so a partial window never over-fetches.

**Scheduling choice.** Rolling window was chosen over level-synchronous BFS. A
level barrier makes one slow page stall a whole level's worth of workers — with
a 10 s timeout and 8 workers, that is 8 idle slots. The rolling window needs one
lock; the barrier needs none. The lock is the cheaper price.

**Connection pool.** The existing `HTTPAdapter` uses urllib3's default
`pool_maxsize=10`. It must be set to `max(N, 10)`, or concurrency above 10
silently serializes behind a full pool and emits warnings.

**Accepted tradeoff.** Crawl order becomes nondeterministic. When `max_pages` is
below a site's total page count, *which* pages land in the report can vary
between runs. This is inherent to concurrent crawling, and it changes how two
runs should be compared.

## §2 Politeness — `_RateLimiter`

A per-host token bucket, consulted inside the worker before `session.get`:

- Minimum interval is `max(user delay, robots.txt Crawl-delay)`. The existing
  `RobotFileParser` already exposes `crawl_delay()`; it is currently unused.
- On `429` or `503`, double the interval (capped at ~2 s), decaying back toward
  baseline after sustained 2xx responses.

This layers over the existing urllib3 `Retry` rather than replacing it. Its
purpose is the WAF risk: `…/divisions/kiryluk/contact.php` already returns a
`409` to a plain `requests` user agent, so at least one host in scope inspects
traffic.

Worker count is exposed as a sidebar slider, default 8, capped at 16.

## §3 Conditional requests — revalidate and reuse

`PageData` gains three fields, all carried through `to_dict()`:

| Field | Meaning |
|---|---|
| `etag` | `ETag` response header, if any |
| `last_modified` | `Last-Modified` response header, if any |
| `from_cache` | True when the record was reused after a 304 |

`Crawler` takes `cached_pages: dict[url → page_dict]`. `app.py` passes this
instead of `seed_visited`; the old parameter remains for backward compatibility.

Per known URL, send `If-None-Match` / `If-Modified-Since`, then:

- **304** — reuse the stored record verbatim, set `from_cache=True`, and
  re-enqueue its stored `internal_links` so the spider keeps moving. The record
  keeps its **stored** `status_code` (200), *not* 304, so `detect_seo_issues`
  does not invent a bogus "HTTP 304" issue. This branch must be handled
  **before** the `content-type` gate in `_fetch`, because a 304 carries no body
  and no content-type.
- **200** — re-parse, replace the record, capture the new validators.
- **Unknown URL** — normal fetch path.

**Schema compatibility.** `parse_export_jsonl` performs no field validation and
`build_export_jsonl` dumps dicts as-is, so the new fields are additive in both
directions: older exports simply lack validators and fall back to unconditional
GETs, and older readers ignore the new keys. The schema version stays
`linkup_export.v1`.

**UI.** Same file uploader, plus a caption reporting how many cached pages will
be revalidated, and the worker slider from §2.

## Error handling

- Per-page exceptions stay confined to `_fetch`, which already converts them
  into a `PageData` carrying an `error` string. A failing worker therefore
  yields a row rather than killing the crawl.
- A future that raises outside `_fetch` is caught by the driver, recorded as an
  errored `PageData` for that URL, and the crawl continues.
- A 304 for a URL missing from `cached_pages` (possible if a caller passes
  validators without records) is treated as a cache miss and refetched
  unconditionally.

## Testing

- **Parallel correctness** — fake session serving a canned link graph: every
  reachable page crawled exactly once, no duplicates, `max_pages` respected
  exactly, at 8 workers.
- **No head-of-line blocking** — one page blocks on a `threading.Event`; assert
  other pages complete past it. Event-based, not sleep-based, so it will not
  flake in CI.
- **Rate limiter** — minimum interval honored; a 429 widens it; sustained 2xx
  decays it.
- **Conditional requests** — 304 reuses the record, sets `from_cache`, keeps
  stored status, and re-enqueues stored links; 200 replaces the record; absent
  validators produce an unconditional GET.
- **Regression** — all 29 existing tests keep passing, including the
  post-redirect base-URL tests from `8c9d7d4`.

## Deferred ideas

Surveyed during brainstorming, deliberately out of scope:

- **Directory-slash normalization.** `_normalize` strips trailing slashes, so
  every folder URL pays an extra 301 hop. Worth doing; independent of this work.
- **Progress-bar throttling.** `progress_bar.progress()` fires a websocket
  rerender per page; at 20k pages that is browser-side overhead.
- **Response body size cap.** Content-type is checked before `resp.text`, but
  there is no byte ceiling.
- **Vectorizing `detect_seo_issues`.** Currently `df.iterrows()`; invisible
  below ~1k pages.

## Measured results (2026-09-14, post-implementation)

30 pages of `columbiamedicine.org/divisions/kiryluk/`, wall clock:

| workers | delay | time | ms/page |
|---|---|---|---|
| 1 | 0.10 | 3.03 s | 101 |
| 8 | 0.10 | 3.14 s | 105 |
| 8 | 0.05 | 1.61 s | 54 |
| 8 | 0.00 | 0.47 s | 16 |
| 1 | 0.00 | 1.53 s | 51 |

**The politeness delay, not the worker count, is the binding constraint.** This
host answers in ~50 ms, so a 0.1 s shared minimum interval caps the crawl at 10
pages/sec regardless of worker count — at `delay=0.1` the 8-worker run is no
faster than serial. With the gate open the parallel win is real: **3.3x**
(1.53 s → 0.47 s). The design's original 4–6x estimate assumed the 200–400 ms
per-page latency measured on a cold single request; warm, this host is ~4x
faster than that, which moves the bottleneck onto the gate.

Consequence for the UI: `delay` is exposed as a control rather than hard-coded
at 0.1, because it is the knob that actually governs throughput. Default stays
0.1 (unchanged request rate against Columbia hosts); 0.02–0.05 unlocks the
parallel gain on servers known to tolerate it.

**Conditional requests are host-dependent:**

- `columbiamedicine.org` sends no `ETag` and no `Last-Modified` at all, so
  revalidation is a no-op there and re-crawls cost full downloads.
- `www.vagelos.columbia.edu` (nginx/Drupal) sends both, and the crawler earns
  real 304 reuse — but only intermittently (3 of 6 identical warm requests),
  with `X-Drupal-Cache: MISS` on the 200s. The ETag itself is stable across 12
  requests, so this is the origin alternating between backends that do and do
  not honour the validator, not a client-side defect.
- `www.columbia.edu` (Cloudflare) sends no validators either.

Savings on re-crawls therefore range from zero to substantial depending on the
host. The completeness benefit — cached pages appearing in the report and their
stored links keeping the spider moving — applies regardless.

## §4 Host scope — found during verification, fixed

`_same_domain` compares against `base_netloc` taken from the **start** URL, so a
host that redirects www/non-www breaks the crawl. `https://vagelos.columbia.edu`
301s to `https://www.vagelos.columbia.edu`, whose absolute links are then all
classified external: 109 external links, 0 internal, crawl ends after 1 page.
This affected the app's own default start URL — the same class of bug as the
post-redirect base-URL fix in `8c9d7d4`.

Resolved with both halves of the semantics:

- `_host_key` folds `www.` and case, so `example.com` and `www.example.com` are
  one site. Other subdomains (`blog.example.com`) stay external.
- `_adopt_redirect_host` takes the **start URL's** post-redirect host as the site
  under crawl, so a start URL that redirects cross-domain still spiders. Scoped
  to the start URL: a later page redirecting off-site cannot widen the crawl.
- `_dedupe_key` folds the www variant for `visited` membership so one page is not
  crawled and reported twice, while the reported URL stays the one actually
  fetched.

Verified live: `https://vagelos.columbia.edu` went from **1 page** (82 internal
links misfiled as external) to 15 pages with no duplicate row.
