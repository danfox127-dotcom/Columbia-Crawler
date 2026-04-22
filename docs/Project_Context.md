# Columbia-Crawler: Project Context

## Core Vibe
**Lightweight, practical SEO crawler** — a Streamlit-based alternative to ScreamingFrog. Designed for healthcare/medical content auditing with an emphasis on rapid diagnosis and AI-powered remediation suggestions.

## Business Goal
Provide Columbia University and healthcare organizations with a **free, open-source SEO crawler** that:
- Scans websites for SEO issues (missing meta tags, duplicate content, low word counts)
- Identifies health-related content gaps and on-page optimization problems
- Uses Gemini AI to suggest corrected titles and meta descriptions
- Exports findings for downstream SEO strategy

## Tech Stack
| Layer | Technology |
|-------|------------|
| **UI Framework** | Streamlit 1.42.0+ |
| **Language** | Python 3.8+ |
| **Primary Crawler** | Scrapy (with fallback to Requests + BeautifulSoup) |
| **HTTP Client** | Requests |
| **HTML Parsing** | BeautifulSoup4 |
| **Data Handling** | Pandas |
| **Concurrency** | ThreadPoolExecutor (10 workers for sitemap scanning) |
| **AI Integration** | Google Gemini 2.5 Flash API |
| **Deployment** | HuggingFace Spaces (Streamlit SDK) |

## Architecture & Data Flow

### High-Level System Components
```
┌─────────────────┐
│   User Input    │  (URL, max pages, excluded paths)
└────────┬────────┘
         │
    ┌────▼────┐
    │ Mode    │
    │ Select  │
    └────┬────┴────┐
         │         │
    ┌────▼────┐  ┌─▼──────────┐
    │  Crawl  │  │  Sitemap   │
    │  Mode   │  │  Scanner   │
    └────┬────┘  └─┬──────────┘
         │         │
    ┌────▼────┐  ┌─▼──────────┐
    │ Scrapy  │  │ Fetch XML  │
    │ (Spider)│  │ Recursively│
    └────┬────┘  └─┬──────────┘
         │         │
    ┌────▼─────────▼────┐
    │  HTML Parsing     │  (Extract title, H1, meta desc, word count)
    │  + Filtering      │  (Exclude banned extensions, paths)
    └────┬──────────────┘
         │
    ┌────▼─────────────────┐
    │ SEO Issue Detection  │  (Duplicate titles, missing meta, low word count, etc.)
    └────┬─────────────────┘
         │
    ┌────▼──────────────┐
    │  Display Results  │  (3 tabs: All Pages, Issues, AI Suggestions)
    │  (Pandas DF)      │
    └────┬──────────────┘
         │
    ┌────▼──────────────┐
    │ Gemini API Call   │  (Optional: AI-powered corrections)
    │ (Selected rows)   │  (Capped at 20 pages per request)
    └────┬──────────────┘
         │
    ┌────▼──────────────┐
    │ Export (CSV)      │  (Results + issues + suggestions)
    └───────────────────┘
```

### Key Data Structures
- **Raw Crawl Output** (JSONL): `{'url', 'status', 'title', 'h1', 'meta_desc', 'word_count'}`
- **Issues DataFrame**: Adds computed `'issues'` (list of SEO violations) and `'issue_count'`
- **Gemini Prompt**: Markdown-formatted list of pages + current metadata + detected issues

### Crawler Modes
1. **🕷️ Crawl Site**: Scrapy-based spider traversing from a start URL
   - Default fallback: Requests + BeautifulSoup queue-based crawler
   - Respects `CLOSESPIDER_PAGECOUNT` limit, `CONCURRENT_REQUESTS=16`

2. **🗺️ Scan Sitemap**: Recursive XML parser (supports sitemap indexes)
   - Fetches all `<loc>` URLs up to max count
   - ThreadPoolExecutor with 10 workers for parallel HTTP checks
   - Respects depth limit (4 levels) to prevent infinite recursion

### SEO Issue Rules
- **Title**: Must be 30–60 chars; flagged if missing, duplicate, or outside range
- **Meta Description**: Must be 50–160 chars; flagged if missing, duplicate, or outside range
- **H1**: Flagged if missing
- **Word Count**: Flagged if < 300 words
- **HTTP Status**: Flagged if not 200/301/302

## Core Files
| File | Purpose |
|------|---------|
| `app.py` | Main Streamlit app; orchestrates all UX and logic |
| `spider_script.py` | (Generated) Scrapy spider for site crawling |
| `auditor.py` | Placeholder for healthcare-specific audit rules (future) |
| `ai_advisor.py` | Placeholder for expanded AI integration (future) |
| `.env.example` | Environment variable template (GEMINI_API_KEY) |

## WIP State

### Completed Features
- ✅ Dual crawl modes (Scrapy + fallback)
- ✅ Sitemap scanning with recursive index support
- ✅ SEO issue detection (titles, meta, H1, word count, duplicates)
- ✅ Folder exclusion (top-level path filtering)
- ✅ 20k URL support (sitemap mode)
- ✅ Live UI progress updates
- ✅ Interactive row selection (capped at 20)
- ✅ Gemini AI suggestions for SEO corrections
- ✅ CSV export (results + issues)

### In Progress / Planned
- [ ] Healthcare-specific issue detection (`auditor.py` expansion)
- [ ] Advanced AI advisor modes (`ai_advisor.py` expansion)
- [ ] Bulk keyword research integration
- [ ] Content gap analysis (comparing site structure to competitors)
- [ ] Mobile-friendliness & Core Web Vitals checks
- [ ] Scheduled crawls + email reporting

### Known Constraints
- Gemini API calls limited to 20 pages per request (UI cap)
- Scrapy spider generation is runtime; requires Python + Scrapy installed
- Sitemap depth capped at 4 to prevent runaway recursion
- Word count is text-only (no script/style tags)

---

**Last Updated**: 2026-04-21
