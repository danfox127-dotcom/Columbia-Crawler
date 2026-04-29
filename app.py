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

# --- 1. SET PAGE CONFIG ---
st.set_page_config(page_title="Healthcare SEO Crawler", page_icon="🕷️", layout="wide")

# --- 5. SITEMAP SCANNER ---
def fetch_sitemap_urls(sitemap_url, max_urls, excluded_paths=None):
    """Recursively fetch all <loc> URLs from a sitemap or sitemap index."""
    excluded = [p.strip().strip('/') for p in (excluded_paths or []) if p.strip()]
    urls = []
    seen_sitemaps = set()

    def _fetch(url, depth=0):
        if depth > 4 or url in seen_sitemaps or len(urls) >= max_urls:
            return
        seen_sitemaps.add(url)
        try:
            resp = requests.get(url, timeout=15, headers={'User-Agent': 'Mozilla/5.0'})
            resp.raise_for_status()
        except Exception:
            return
        try:
            root = ET.fromstring(resp.content)
        except ET.ParseError:
            return

        ns = root.tag.split('}')[0].lstrip('{') if '}' in root.tag else ''
        pre = f'{{{ns}}}' if ns else ''
        tag = root.tag.split('}')[-1]

        if tag == 'sitemapindex':
            for sm in root.findall(f'{pre}sitemap'):
                loc = sm.find(f'{pre}loc')
                if loc is not None and loc.text:
                    _fetch(loc.text.strip(), depth + 1)
                    if len(urls) >= max_urls:
                        return
        else:  # urlset
            for url_el in root.findall(f'{pre}url'):
                loc = url_el.find(f'{pre}loc')
                if loc is None or not loc.text:
                    continue
                page_url = loc.text.strip()
                parsed = urlparse(page_url)
                path_parts = parsed.path.strip('/').split('/')
                if excluded and path_parts and path_parts[0] in excluded:
                    continue
                urls.append(page_url)
                if len(urls) >= max_urls:
                    return

    _fetch(sitemap_url)
    return urls


def _check_url(args):
    url, session = args
    try:
        resp = session.get(url, timeout=10)
        status = resp.status_code
        if status != 200 or not resp.text:
            return {'url': url, 'status': status, 'title': '', 'h1': '', 'meta_desc': '', 'word_count': 0}
        soup = BeautifulSoup(resp.text, 'html.parser')
        title = soup.title.string.strip() if soup.title and soup.title.string else ''
        h1_tag = soup.find('h1')
        h1 = h1_tag.get_text(strip=True) if h1_tag else ''
        meta_tag = soup.find('meta', attrs={'name': 'description'})
        meta_desc = (meta_tag.get('content') or '').strip() if meta_tag else ''
        body = soup.find('body')
        word_count = len(body.get_text(separator=' ', strip=True).split()) if body else 0
        return {'url': url, 'status': status, 'title': title, 'h1': h1, 'meta_desc': meta_desc, 'word_count': word_count}
    except Exception:
        return {'url': url, 'status': 0, 'title': '', 'h1': '', 'meta_desc': '', 'word_count': 0}


def scan_sitemap(sitemap_url, max_urls, excluded_paths, progress_bar):
    urls = fetch_sitemap_urls(sitemap_url, max_urls, excluded_paths)
    if not urls:
        return pd.DataFrame(), 0

    session = requests.Session()
    session.headers.update({'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'})
    results = [None] * len(urls)
    completed = 0

    with ThreadPoolExecutor(max_workers=10) as executor:
        future_to_idx = {executor.submit(_check_url, (url, session)): i for i, url in enumerate(urls)}
        for future in as_completed(future_to_idx):
            idx = future_to_idx[future]
            results[idx] = future.result()
            completed += 1
            progress_bar.progress(completed / len(urls), text=f"Checked {completed}/{len(urls)} URLs")

    return pd.DataFrame(results), len(urls)


# --- 6. SEO ISSUE DETECTION ---
def detect_seo_issues(df):
    dup_titles = set(df['title'][df['title'].str.strip() != ''].value_counts()[lambda x: x > 1].index)
    dup_metas  = set(df['meta_desc'][df['meta_desc'].str.strip() != ''].value_counts()[lambda x: x > 1].index)

    rows = []
    for _, row in df.iterrows():
        issues = []
        title  = str(row.get('title', '') or '')
        meta   = str(row.get('meta_desc', '') or '')
        h1     = str(row.get('h1', '') or '')
        wc     = int(row.get('word_count', 0) or 0)
        status = int(row.get('status', 200) or 200)

        if not title:
            issues.append('Missing title')
        elif len(title) < 30:
            issues.append(f'Title too short ({len(title)} chars, min 30)')
        elif len(title) > 60:
            issues.append(f'Title too long ({len(title)} chars, max 60)')
        if title in dup_titles:
            issues.append('Duplicate title')

        if not meta:
            issues.append('Missing meta description')
        elif len(meta) < 50:
            issues.append(f'Meta desc too short ({len(meta)} chars, min 50)')
        elif len(meta) > 160:
            issues.append(f'Meta desc too long ({len(meta)} chars, max 160)')
        if meta in dup_metas:
            issues.append('Duplicate meta description')

        if not h1:
            issues.append('Missing H1')
        if wc < 300:
            issues.append(f'Low word count ({wc} words)')
        if status not in (200, 301, 302):
            issues.append(f'HTTP {status}')

        rows.append({
            'url': row['url'], 'status': status, 'title': title,
            'h1': h1, 'meta_desc': meta, 'word_count': wc,
            'issues': '; '.join(issues), 'issue_count': len(issues),
        })

    return pd.DataFrame(rows)


# --- 7. GEMINI AI CORRECTIONS ---
def call_gemini(prompt, api_key):
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    payload = {"contents": [{"parts": [{"text": prompt}]}]}
    resp = requests.post(url, json=payload, timeout=60)
    resp.raise_for_status()
    return resp.json()['candidates'][0]['content']['parts'][0]['text']


def build_gemini_prompt(issues_df):
    lines = ["You are an SEO expert. For each page below, suggest a corrected title and meta description that fix the listed issues. Be concise and specific to healthcare/medical content.\n"]
    for _, row in issues_df.iterrows():
        lines.append(f"URL: {row['url']}")
        lines.append(f"Current title: {row['title'] or '(none)'}")
        lines.append(f"Current meta desc: {row['meta_desc'] or '(none)'}")
        lines.append(f"Current H1: {row['h1'] or '(none)'}")
        lines.append(f"Issues: {row['issues']}")
        lines.append("---")
    lines.append("\nFor each URL provide:\n- Suggested title (30-60 chars)\n- Suggested meta description (50-160 chars)\n- One-line reason for each change")
    return "\n".join(lines)


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


# --- 8. APP LAYOUT & UI ---
st.title("🕷️ Live SEO Crawler")
st.markdown("Crawl a site or scan a sitemap — detect SEO issues and get AI-powered correction suggestions.")

for key in ('df', 'issues_df', 'gemini_response', 'crawl_pages', 'crawl_meta', 'resume_pages'):
    if key not in st.session_state:
        st.session_state[key] = None

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
        help="Top-level folder names to skip, e.g. /news/ — applies to both crawl and sitemap modes",
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

# --- 9. EXECUTION ---
if start_button:
    if not target_url:
        st.error("Please enter a URL.")
    else:
        excluded_paths = [p for p in st.session_state.get("exclude_paths_raw", "").splitlines() if p.strip()]
        st.session_state.df = None
        st.session_state.issues_df = None
        st.session_state.gemini_response = None
        st.session_state.crawl_pages = None
        st.session_state.crawl_meta = None

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

        else:  # Sitemap mode
            st.info(f"Fetching sitemap URLs from {target_url}...")
            progress_bar = st.progress(0, text="Starting...")
            try:
                df_sitemap, total = scan_sitemap(
                    target_url,
                    int(max_pages_input) if max_pages_input > 0 else 999999,
                    excluded_paths,
                    progress_bar
                )
                progress_bar.empty()
                if not df_sitemap.empty:
                    st.session_state.df = df_sitemap
                    st.session_state.crawl_pages = None
                    st.session_state.crawl_meta = {
                        "start_url": target_url,
                        "crawl_mode": "sitemap",
                        "max_pages": int(max_pages_input) if max_pages_input > 0 else 999999,
                        "exclude_paths": excluded_paths,
                    }
                else:
                    st.warning("No URLs found in the sitemap or all were excluded.")
            except Exception as e:
                st.error(f"Sitemap scan failed: {e}")

        if st.session_state.df is not None:
            st.session_state.issues_df = detect_seo_issues(st.session_state.df)

# --- 10. DISPLAY RESULTS ---
if st.session_state.df is not None:
    df = st.session_state.df
    issues_df = st.session_state.issues_df

    tab1, tab2, tab3 = st.tabs(["📊 All Pages", "⚠️ SEO Issues", "🤖 Gemini Suggestions"])

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

    with tab2:
        flagged = issues_df[issues_df['issue_count'] > 0].sort_values('issue_count', ascending=False)
        clean   = issues_df[issues_df['issue_count'] == 0]

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("Total Pages", len(issues_df))
        c2.metric("Pages with Issues", len(flagged))
        c3.metric("Clean Pages", len(clean))
        c4.metric("Total Issues", int(issues_df['issue_count'].sum()))

        if len(flagged):
            issue_types = {}
            for chunk in '; '.join(flagged['issues'].tolist()).split('; '):
                key = chunk.split('(')[0].strip()
                if key:
                    issue_types[key] = issue_types.get(key, 0) + 1
            st.subheader("Issue Breakdown")
            st.dataframe(
                pd.DataFrame(list(issue_types.items()), columns=['Issue', 'Count']).sort_values('Count', ascending=False),
                use_container_width=True, hide_index=True
            )
            st.subheader("Flagged Pages")
            st.dataframe(flagged[['url', 'title', 'meta_desc', 'h1', 'word_count', 'issues']],
                         use_container_width=True, hide_index=True)
            st.download_button("Download Issues CSV",
                               flagged.to_csv(index=False).encode('utf-8'),
                               file_name="seo_issues.csv", mime="text/csv")
        else:
            st.success("No SEO issues found!")

    with tab3:
        flagged = issues_df[issues_df['issue_count'] > 0].sort_values('issue_count', ascending=False).reset_index(drop=True)
        if flagged.empty:
            st.info("No issues found — nothing for Gemini to fix.")
        else:
            st.markdown(f"**Select up to 20 rows** to send to Gemini. {len(flagged)} pages have issues — sorted by most issues first.")

            selection = st.dataframe(
                flagged[['url', 'title', 'meta_desc', 'h1', 'word_count', 'issues']],
                use_container_width=True,
                hide_index=False,
                on_select="rerun",
                selection_mode="multi-row",
            )

            selected_indices = selection.selection.rows if selection.selection.rows else []
            if len(selected_indices) > 20:
                st.warning(f"You selected {len(selected_indices)} rows — only the first 20 will be sent to Gemini.")
                selected_indices = selected_indices[:20]

            col_a, col_b = st.columns([3, 1])
            with col_a:
                st.caption(f"{len(selected_indices)} page(s) selected" if selected_indices else "No rows selected — click rows above to choose pages.")
            with col_b:
                analyze_button = st.button("✨ Analyze with Gemini", use_container_width=True, disabled=(len(selected_indices) == 0))

            if analyze_button:
                if not gemini_key:
                    st.error("Add your Gemini API key in the sidebar or set GEMINI_API_KEY in HF Secrets.")
                else:
                    chosen = flagged.iloc[selected_indices]
                    prompt = build_gemini_prompt(chosen)
                    with st.spinner(f"Asking Gemini to analyse {len(chosen)} page(s)..."):
                        try:
                            st.session_state.gemini_response = call_gemini(prompt, gemini_key)
                        except Exception as e:
                            st.error(f"Gemini API error: {e}")

            if st.session_state.gemini_response:
                st.subheader("Gemini's Suggested Corrections")
                st.markdown(st.session_state.gemini_response)
                st.download_button("Download Suggestions",
                                   st.session_state.gemini_response.encode('utf-8'),
                                   file_name="gemini_suggestions.txt", mime="text/plain")
